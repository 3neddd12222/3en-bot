import os
import asyncio
import discord
from discord.ext import commands, tasks
from flask import Flask
from threading import Thread

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
    """يتأكد أن البوت يشغّل الصوت الصامت حتى لا يُعتبر خامل (Idle)."""
    if vc and vc.is_connected() and not vc.is_playing():
        try:
            vc.play(SilentAudio())
        except discord.ClientException:
            pass


async def connect_to_target(reason: str = ""):
    """يحاول الاتصال (أو إعادة الاتصال) بالروم الصوتي المستهدف."""
    global TARGET_VOICE_CHANNEL_ID, TARGET_GUILD_ID

    if not TARGET_VOICE_CHANNEL_ID or not TARGET_GUILD_ID:
        return

    guild = bot.get_guild(TARGET_GUILD_ID)
    if not guild:
        return

    channel = guild.get_channel(TARGET_VOICE_CHANNEL_ID)
    if not channel:
        return

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
    except Exception as e:
        print(f"❌ تعذر الاتصال بالروم الصوتي: {e}")


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
        await ctx.reply("❌ يا طويل العمر، ادخل روم صوتي أولاً!", mention_author=True)
        return

    channel = ctx.author.voice.channel
    TARGET_VOICE_CHANNEL_ID = channel.id
    TARGET_GUILD_ID = ctx.guild.id

    await connect_to_target()

    await ctx.reply(
        f"🔊 أشرت علي ودخلت معك روم: **{channel.name}** ومتكي معك للصبح، ما أطلع حتى لو فضي الروم!",
        mention_author=True
    )


@bot.command(name='leave', aliases=['طلع', 'out'])
async def leave(ctx):
    global TARGET_VOICE_CHANNEL_ID, TARGET_GUILD_ID
    TARGET_VOICE_CHANNEL_ID = None
    TARGET_GUILD_ID = None

    if ctx.voice_client:
        await ctx.voice_client.disconnect(force=True)
        await ctx.reply("👋 أشرت علي وطلعت، نشوفك على خير!", mention_author=True)
    else:
        await ctx.reply("❌ أنا أساساً ماني في أي روم صوتي!", mention_author=True)


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
