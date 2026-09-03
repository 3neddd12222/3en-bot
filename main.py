from __future__ import annotations  # يخلي type hints متوافقة حتى مع بايثون أقدم من 3.10

import os
import asyncio
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread
import yt_dlp

# --- 1. خادم ويب مصغر (Flask) لإبقاء البوت متصلاً 24/7 على Render ---
app = Flask('')


@app.route('/')
def home():
    return "Bot is Alive 24/7!"


def run_flask():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()


# --- 2. إعدادات البوت والـ Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="$", intents=intents)

# رتبة الأدمن الخاصة بك
ADMIN_ROLE_ID = 1544759188289359944

# متغير لحفظ رقم الروم الصوتي المستهدف للترافيك (والسيرفر الخاص به)
TARGET_VOICE_CHANNEL_ID = None
TARGET_GUILD_ID = None


# مصدر صوتي صامت بذبذبات مستمرة لمنع طرد البوت وإبقائه متصلاً للأبد
class SilentAudio(discord.AudioSource):
    def read(self):
        return b'\xf8\xff\xfe' + b'\x00' * 381


async def ensure_playing(vc: discord.VoiceClient):
    """يتأكد أن البوت يشغّل الصوت الصامت حتى لا يُعتبر خامل (Idle) -- فقط إذا ما فيه أغنية شغالة أو موقوفة مؤقتاً."""
    if vc and vc.is_connected() and not vc.is_playing() and not vc.is_paused():
        try:
            vc.play(SilentAudio())
        except discord.ClientException:
            pass


async def connect_to_target(reason: str = "") -> tuple[bool, str]:
    """يحاول الاتصال (أو إعادة الاتصال) بالروم الصوتي المستهدف.
    يرجع (نجح, رسالة الخطأ إن وجدت) عشان الأوامر تقدر تبلغ المستخدم بدقة."""
    global TARGET_VOICE_CHANNEL_ID, TARGET_GUILD_ID

    if not TARGET_VOICE_CHANNEL_ID or not TARGET_GUILD_ID:
        return False, "ما فيه روم مستهدف محفوظ."

    guild = bot.get_guild(TARGET_GUILD_ID)
    if not guild:
        return False, "تعذر إيجاد السيرفر."

    channel = guild.get_channel(TARGET_VOICE_CHANNEL_ID)
    if not channel:
        return False, "الروم الصوتي غير موجود (ممكن انحذف)."

    existing_vc = guild.voice_client
    try:
        if existing_vc and existing_vc.is_connected():
            if existing_vc.channel.id != channel.id:
                await existing_vc.move_to(channel)
            vc = existing_vc
        else:
            vc = await channel.connect(reconnect=True, timeout=15)

        await ensure_playing(vc)
        if reason:
            print(f"🔄 {reason} — البوت متصل الآن في: {channel.name}")
        return True, ""
    except discord.ClientException as e:
        # الخطأ الأشهر هنا: مكتبة PyNaCl غير مثبتة (مطلوبة إلزامياً لصوت Discord)
        msg = f"فشل اتصال الصوت: {e} — تأكد إنك مثبت مكتبة PyNaCl (pip install PyNaCl)."
        print(f"❌ {msg}")
        return False, msg
    except asyncio.TimeoutError:
        msg = "انتهت مهلة الاتصال بالروم الصوتي (Timeout)."
        print(f"❌ {msg}")
        return False, msg
    except discord.Forbidden:
        msg = "البوت ما عنده صلاحية الدخول للروم الصوتي (Connect/Speak)."
        print(f"❌ {msg}")
        return False, msg
    except Exception as e:
        msg = f"خطأ غير متوقع أثناء الاتصال: {e}"
        print(f"❌ {msg}")
        return False, msg


# ==========================================
# 🎵 نظام تشغيل الأغاني (بدون أي أداة خارجية غير yt-dlp + ffmpeg)
# ==========================================

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 192k',
}

music_queues: dict[int, list[dict]] = {}
music_history: dict[int, list[dict]] = {}
now_playing: dict[int, dict | None] = {}
music_channels: dict[int, discord.abc.Messageable] = {}  # آخر روم كتابي استخدم فيه $play، عشان نرسل فيه تحديثات "يشتغل الحين"


def now_playing_embed(track: dict) -> discord.Embed:
    embed = discord.Embed(
        title="🎶 يشتغل الحين",
        description=f"**{track['title']}**",
        color=discord.Color.green()
    )
    if track.get('webpage_url'):
        embed.add_field(name="🔗 الرابط", value=track['webpage_url'], inline=False)
    if track.get('requester'):
        embed.set_footer(text=f"طلبها: {track['requester']}")
    return embed


# --- منطق التحكم بالأغاني (تستخدمه الأوامر النصية والأزرار مع بعض) ---
async def do_pause(guild: discord.Guild) -> str:
    vc = guild.voice_client
    if vc and now_playing.get(guild.id) and vc.is_playing():
        vc.pause()
        return "⏸️ تم إيقاف الأغنية مؤقتاً."
    return "ℹ️ ما فيه أغنية شغالة حالياً."


async def do_resume(guild: discord.Guild) -> str:
    vc = guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        return "▶️ تم استئناف الأغنية."
    return "ℹ️ ما فيه أغنية موقوفة مؤقتاً."


async def do_skip(guild: discord.Guild) -> str:
    vc = guild.voice_client
    if vc and now_playing.get(guild.id):
        title = now_playing[guild.id]['title']
        vc.stop()  # يشغل تلقائياً التالي عن طريق after_playing
        return f"⏭️ تم تخطي: **{title}**"
    return "ℹ️ ما فيه أغنية أتخطاها."


async def do_back(guild: discord.Guild) -> str:
    history = music_history.get(guild.id, [])
    vc = guild.voice_client

    if len(history) < 2:
        return "ℹ️ ما فيه أغنية سابقة بالسجل."

    history.pop()  # نشيل الحالية
    prev_track = history.pop()  # نجيب اللي قبلها

    music_queues.setdefault(guild.id, []).insert(0, prev_track)

    if vc and now_playing.get(guild.id):
        vc.stop()
    else:
        await play_next(guild, announce=False)

    return f"⏮️ نرجّع الأغنية السابقة: **{prev_track['title']}**"


async def do_stopmusic(guild: discord.Guild) -> str:
    music_queues[guild.id] = []
    now_playing[guild.id] = None
    vc = guild.voice_client
    if vc:
        vc.stop()
        await ensure_playing(vc)
    return "🔇 تم إيقاف كل الأغاني والرجوع للوضع الصامت (البوت باقٍ بالروم)."


# --- لوحة أزرار تحكم بالأغاني (تظهر تحت رسالة "يشتغل الحين") ---
class MusicView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="music_pause_resume")
    async def pause_resume_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            msg = await do_pause(interaction.guild)
        elif vc and vc.is_paused():
            msg = await do_resume(interaction.guild)
        else:
            msg = "ℹ️ ما فيه أغنية شغالة."
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="music_skip")
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = await do_skip(interaction.guild)
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="music_back")
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = await do_back(interaction.guild)
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music_stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg = await do_stopmusic(interaction.guild)
        await interaction.response.send_message(msg, ephemeral=True)


def _extract_track_sync(query: str) -> dict:
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        info = ydl.extract_info(query, download=False)
        if 'entries' in info:
            info = info['entries'][0]
        return {
            'title': info.get('title', 'مقطع بدون اسم'),
            'stream_url': info['url'],
            'webpage_url': info.get('webpage_url', query),
        }


async def extract_track(query: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract_track_sync, query)


async def play_next(guild: discord.Guild, announce: bool = True):
    """يشغل أول أغنية بالطابور، ولو ما فيه شي يرجع للصوت الصامت (بدون خروج من الروم).
    announce=True يرسل إشعار "يشتغل الحين" تلقائياً بالروم الكتابي (يُستخدم عند التخطي التلقائي لنهاية الأغنية)."""
    vc = guild.voice_client
    if not vc or not vc.is_connected():
        return

    queue = music_queues.setdefault(guild.id, [])
    if queue:
        track = queue.pop(0)
        now_playing[guild.id] = track

        history = music_history.setdefault(guild.id, [])
        history.append(track)
        if len(history) > 20:
            history.pop(0)

        source = discord.FFmpegPCMAudio(track['stream_url'], **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(source, volume=0.6)

        def after_playing(error):
            if error:
                print(f"⚠️ خطأ أثناء تشغيل الأغنية: {error}")
            fut = asyncio.run_coroutine_threadsafe(play_next(guild, announce=True), bot.loop)
            try:
                fut.result()
            except Exception as e:
                print(f"⚠️ خطأ بعد انتهاء التشغيل: {e}")

        vc.play(source, after=after_playing)

        if announce:
            channel = music_channels.get(guild.id)
            if channel:
                try:
                    await channel.send(embed=now_playing_embed(track), view=MusicView())
                except Exception as e:
                    print(f"⚠️ تعذر إرسال إشعار الأغنية: {e}")
    else:
        now_playing[guild.id] = None
        await ensure_playing(vc)


# --- مراقبة دورية احتياطية (Watchdog) بجانب on_voice_state_update ---
@tasks.loop(seconds=20)
async def voice_watchdog():
    if not TARGET_VOICE_CHANNEL_ID or not TARGET_GUILD_ID:
        return

    guild = bot.get_guild(TARGET_GUILD_ID)
    if not guild:
        return

    vc = guild.voice_client
    if not vc or not vc.is_connected():
        await connect_to_target("الووتشدوغ اكتشف انفصال البوت")
    else:
        await ensure_playing(vc)


@voice_watchdog.before_loop
async def before_watchdog():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    print(f"✅ تم تشغيل بوت الترافيك بنجاح: {bot.user}")
    bot.add_view(MusicView())  # يخلي الأزرار تشتغل حتى بعد إعادة تشغيل البوت
    if not voice_watchdog.is_running():
        voice_watchdog.start()


# --- الأحداث التلقائية للروم الصوتي والترحيب ---
@bot.event
async def on_voice_state_update(member, before, after):
    # 1. نظام إعادة الاتصال التلقائي للبوت إذا تم فصله أو انقطع الاتصال
    if member.id == bot.user.id:
        if before.channel is not None and after.channel is None:
            await asyncio.sleep(5)  # انتظار 5 ثواني ثم إعادة الدخول
            await connect_to_target("تم فصل البوت")
        return

    # تجاهل البوتات الأخرى
    if member.bot:
        return

    # 2. الترحيب عند دخول العضو (يرسل في الشات المدمج للروم الصوتي فقط)
    voice_channel = after.channel
    if not voice_channel:
        return

    text_channel = getattr(voice_channel, 'text_channel', None)

    if before.channel is None and after.channel is not None:
        if text_channel and text_channel.permissions_for(member.guild.me).send_messages:
            try:
                embed = discord.Embed(
                    title="🎙️ مرحباً بك في الروم الصوتي!",
                    description=f"أهلاً بك {member.mention}، أنورت الروم!",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="📜 قائمة الأوامر المتاحة",
                    value=(
                        "• `$bothelp` : عرض قائمة الأوامر الشاملة\n"
                        "• `$join` أو `خش` : تثبيت البوت في الروم الصوتي\n"
                        "• `$leave` أو `طلع` : إخراج البوت من الروم\n"
                        "• `$userinfo` : عرض معلومات حسابك"
                    ),
                    inline=False
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text="3en Bot • متواجدين لخدمتكم")

                await text_channel.send(content=f"👋 {member.mention}", embed=embed)
            except Exception:
                pass


# ==========================================
# 📢 أوامر الأعضاء العامة (General Commands)
# ==========================================

@bot.command(name='bothelp', aliases=['help2'])
async def bothelp(ctx):
    embed = discord.Embed(
        title="📜 قائمة أوامر البوت الشاملة",
        description="جميع الأوامر المتاحة في السيرفر مقسمة حسب الصلاحيات:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="👥 أوامر الأعضاء العامة",
        value=(
            "• `$bothelp` : عرض هذه القائمة\n"
            "• `$join` / `خش` : إدخال البوت لرومك الصوتي وتثبيته\n"
            "• `$leave` / `طلع` : إخراج البوت من الروم الصوتي\n"
            "• `$userinfo [@عضو]` : عرض معلومات الحساب\n"
            "• `$serverinfo` : عرض معلومات السيرفر\n"
            "• `$avatar [@عضو]` : عرض صورة الحساب"
        ),
        inline=False
    )
    embed.add_field(
        name="🎵 أوامر الأغاني",
        value=(
            "• `$play <رابط>` / `شغل` / `بلاي` : تشغيل مقطع من يوتيوب\n"
            "• `$pause` : إيقاف مؤقت\n"
            "• `$resume` / `استمر` / `كمل` : استئناف التشغيل\n"
            "• `$skip` / `تخطي` : تخطي للأغنية التالية\n"
            "• `$back` / `رجع` / `السابقة` : رجوع للأغنية السابقة\n"
            "• `$stopmusic` / `سكت` : إيقاف كل الأغاني (البوت يضل بالروم)\n"
            "• `$queue` / `الطابور` : عرض قائمة الانتظار\n"
            "أو استخدم الأزرار ⏯️ ⏭️ ⏮️ ⏹️ اللي تطلع تحت رسالة 🎶 يشتغل الحين"
        ),
        inline=False
    )
    embed.add_field(
        name="🛡️ أوامر الإدارة (للأدمنية فقط)",
        value=(
            "• `$giverole @عضو @رتبة` : إعطاء رتبة لعضو\n"
            "• `$removerole @عضو @رتبة` : سحب (قشع) رتبة من عضو\n"
            "• `$clear [عدد]` : مسح عدد محدد من الرسائل\n"
            "• `$kick @عضو [السبب]` : طرد عضو من السيرفر\n"
            "• `$ban @عضو [السبب]` : حظر (بان) عضو من السيرفر\n"
            "• `$lock` / `$unlock` : قفل وفك قفل الروم الكتابي\n"
            "• `$ping` : فحص استجابة البوت"
        ),
        inline=False
    )
    embed.set_footer(text="3en Bot • خدمة 24/7")
    await ctx.reply(embed=embed, mention_author=True)


@bot.command(name='join', aliases=['خش'])
async def join(ctx):
    global TARGET_VOICE_CHANNEL_ID, TARGET_GUILD_ID

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.reply("⚠️ لازم تكون داخل روم صوتي أولاً.", mention_author=True)
        return

    channel = ctx.author.voice.channel
    TARGET_VOICE_CHANNEL_ID = channel.id
    TARGET_GUILD_ID = ctx.guild.id

    success, error_msg = await connect_to_target()

    if success:
        await ctx.reply(
            f"✅ تم الدخول والتثبيت في الروم الصوتي: **{channel.name}**\n"
            f"🎧 البوت باقٍ هنا حتى لو خلا الروم.",
            mention_author=True
        )
    else:
        await ctx.reply(
            f"❌ حاولت الدخول لكن فشل الاتصال الصوتي فعلياً.\n"
            f"السبب: `{error_msg}`\n\n"
            f"تأكد من:\n"
            f"• تثبيت مكتبة `PyNaCl` (أضفها لـ requirements.txt)\n"
            f"• أن البوت عنده صلاحية Connect / Speak بهذا الروم\n"
            f"• راجع سجل الكونسول (Logs) للتفاصيل الكاملة",
            mention_author=True
        )


@bot.command(name='leave', aliases=['طلع', 'out'])
async def leave(ctx):
    global TARGET_VOICE_CHANNEL_ID, TARGET_GUILD_ID
    TARGET_VOICE_CHANNEL_ID = None
    TARGET_GUILD_ID = None
    music_queues[ctx.guild.id] = []
    now_playing[ctx.guild.id] = None

    if ctx.voice_client:
        await ctx.voice_client.disconnect(force=True)
        await ctx.reply("👋 تم الخروج من الروم الصوتي، إلى اللقاء.", mention_author=True)
    else:
        await ctx.reply("ℹ️ البوت أساساً مو داخل أي روم صوتي.", mention_author=True)


# ==========================================
# 🎵 أوامر تشغيل الأغاني
# ==========================================

@bot.command(name='play', aliases=['شغل', 'بلاي'])
async def play(ctx, *, query: str = None):
    global TARGET_VOICE_CHANNEL_ID, TARGET_GUILD_ID

    if not query:
        await ctx.reply("⚠️ اكتب رابط المقطع أو اسمه بعد الأمر. مثال: `$play <رابط يوتيوب>`", mention_author=True)
        return

    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.reply("⚠️ لازم تكون داخل روم صوتي أولاً.", mention_author=True)
        return

    # لو البوت مو متصل أصلاً، يدخل روم الشخص تلقائياً ويثبت فيه
    if not ctx.guild.voice_client or not ctx.guild.voice_client.is_connected():
        TARGET_VOICE_CHANNEL_ID = ctx.author.voice.channel.id
        TARGET_GUILD_ID = ctx.guild.id
        success, error_msg = await connect_to_target()
        if not success:
            await ctx.reply(f"❌ تعذر دخول الروم الصوتي: `{error_msg}`", mention_author=True)
            return

    music_channels[ctx.guild.id] = ctx.channel  # نحفظ الروم عشان إشعارات التخطي التلقائي

    vc = ctx.guild.voice_client
    status_msg = await ctx.reply("🔎 جاري البحث وتجهيز المقطع...", mention_author=True)

    try:
        track = await extract_track(query)
    except Exception as e:
        await status_msg.edit(content=f"❌ تعذر جلب المقطع: `{e}`")
        return

    track['requester'] = ctx.author.display_name

    queue = music_queues.setdefault(ctx.guild.id, [])
    queue.append(track)

    if now_playing.get(ctx.guild.id) is None:
        vc.stop()  # يوقف الصوت الصامت لو كان شغال
        await play_next(ctx.guild, announce=False)
        await status_msg.edit(content=None, embed=now_playing_embed(track), view=MusicView())
    else:
        await status_msg.edit(content=f"➕ أضيفت للطابور (رقم {len(queue)}): **{track['title']}**", view=MusicView())


@bot.command(name='pause', aliases=['وقف_مؤقت'])
async def pause(ctx):
    msg = await do_pause(ctx.guild)
    await ctx.reply(msg, mention_author=True)


@bot.command(name='resume', aliases=['استمر', 'كمل'])
async def resume(ctx):
    msg = await do_resume(ctx.guild)
    await ctx.reply(msg, mention_author=True)


@bot.command(name='skip', aliases=['تخطي'])
async def skip(ctx):
    msg = await do_skip(ctx.guild)
    await ctx.reply(msg, mention_author=True)


@bot.command(name='back', aliases=['رجع', 'السابقة'])
async def back(ctx):
    msg = await do_back(ctx.guild)
    await ctx.reply(msg, mention_author=True)


@bot.command(name='stopmusic', aliases=['سكت'])
async def stopmusic(ctx):
    msg = await do_stopmusic(ctx.guild)
    await ctx.reply(msg, mention_author=True)


@bot.command(name='queue', aliases=['الطابور', 'القائمة'])
async def queue_cmd(ctx):
    q = music_queues.get(ctx.guild.id, [])
    now = now_playing.get(ctx.guild.id)

    embed = discord.Embed(title="🎵 طابور الأغاني", color=discord.Color.orange())
    embed.add_field(
        name="▶️ الحين يشتغل",
        value=now['title'] if now else "لا شي (وضع صامت)",
        inline=False
    )
    if q:
        listing = "\n".join(f"{i+1}. {t['title']}" for i, t in enumerate(q[:10]))
        embed.add_field(name="⏭️ التالي بالطابور", value=listing, inline=False)
    else:
        embed.add_field(name="⏭️ التالي بالطابور", value="الطابور فاضي", inline=False)

    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"👤 معلومات الحساب - {member.name}", color=discord.Color.gold())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="الاسم:", value=member.mention, inline=True)
    embed.add_field(name="الـ ID:", value=f"`{member.id}`", inline=True)
    embed.add_field(name="تاريخ انضمامه للسيرفر:", value=member.joined_at.strftime("%Y/%m/%d"), inline=False)
    embed.add_field(name="تاريخ إنشاء الحساب:", value=member.created_at.strftime("%Y/%m/%d"), inline=False)
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"🏰 معلومات سيرفر - {guild.name}", color=discord.Color.purple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="عدد الأعضاء:", value=f"👥 {guild.member_count}", inline=True)
    embed.add_field(name="مالك السيرفر:", value=guild.owner.mention, inline=True)
    embed.add_field(name="تاريخ إنشاء السيرفر:", value=guild.created_at.strftime("%Y/%m/%d"), inline=False)
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"🖼️ صورة {member.name}", color=discord.Color.blue())
    embed.set_image(url=member.display_avatar.url)
    await ctx.reply(embed=embed, mention_author=True)


# ==========================================
# 🛡️ أوامر الإدارة حصرياً لرتبة الأدمن
# ==========================================

@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def giverole(ctx, member: discord.Member, role: discord.Role):
    try:
        await member.add_roles(role)
        await ctx.reply(f"✅ تم إعطاء رتبة **{role.name}** للعضو {member.mention} بنجاح!", mention_author=True)
    except Exception:
        await ctx.reply("❌ تعذر إعطاء الرتبة. تأكد من إعطاء البوت صلاحية إدارة الرتب وأن رتبته أعلى منها.", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    try:
        await member.remove_roles(role)
        await ctx.reply(f"🧹 تم سحب (قشع) رتبة **{role.name}** من العضو {member.mention} بنجاح!", mention_author=True)
    except Exception:
        await ctx.reply("❌ تعذر سحب الرتبة. تأكد من صلاحيات البوت وموقع رتبته.", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def kick(ctx, member: discord.Member, *, reason: str = "لم يتم ذكر سبب"):
    try:
        await member.kick(reason=reason)
        await ctx.reply(f"👞 تم طرد العضو {member.mention} من السيرفر. السبب: `{reason}`", mention_author=True)
    except Exception:
        await ctx.reply("❌ تعذر طرد العضو. تأكد من أن رتبة البوت أعلى من العضو.", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def ban(ctx, member: discord.Member, *, reason: str = "لم يتم ذكر سبب"):
    try:
        await member.ban(reason=reason)
        await ctx.reply(f"🔨 تم حظر (بان) العضو {member.mention} من السيرفر. السبب: `{reason}`", mention_author=True)
    except Exception:
        await ctx.reply("❌ تعذر حظر العضو. تأكد من صلاحيات البوت.", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def ping(ctx):
    await ctx.reply(f"🏓 شغال ياحلو! سرعة الاستجابة: **{round(bot.latency * 1000)}ms**", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسالة يا {ctx.author.mention}!", delete_after=3)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.reply("🔒 تم قفل الروم عن الجميع بنجاح!", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.reply("🔓 تم فك قفل الروم وإتاحته للجميع!", mention_author=True)


@giverole.error
@removerole.error
@kick.error
@ban.error
@ping.error
@clear.error
@lock.error
@unlock.error
async def admin_commands_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.reply("❌ عذراً، هذا الأمر مخصص للإدارة والأدمنية فقط!", mention_author=True)
    else:
        raise error


# تشغيل خادم الويب للحفاظ على الاتصال 24/7
keep_alive()

bot.run(os.environ.get("DISCORD_TOKEN"))
