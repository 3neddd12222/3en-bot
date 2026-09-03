from __future__ import annotations  # يخلي type hints متوافقة حتى مع بايثون أقدم من 3.10

import os
import time
from datetime import timedelta
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# --- 1. خادم ويب مصغر (Flask) لإبقاء البوت متصلاً 24/7 على Render ---
app = Flask('')


@app.route('/')
def home():
    return "Bot is Alive 24/7!"


def run_flask():
    # تعديل البورت هنا عشان يتوافق تلقائياً مع رندر وما يعطيني إيرور Exit status 1
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()


# --- 2. إعدادات البوت والـ Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)

# رتبة الأدمن الوحيدة اللي تتحكم بكل أوامر النظام
ADMIN_ROLE_ID = 1544759188289359944

BOT_START_TIME = time.time()

# سجل بسيط للتحذيرات (بالذاكرة فقط -- يروح إذا البوت أعاد التشغيل)
warnings_log: dict[int, list[dict]] = {}


# ==========================================
# 📢 أوامر الأعضاء العامة (General Commands)
# ==========================================

@bot.command(name='help')
async def help_cmd(ctx):
    """أوامر عامة للجميع فقط -- ما تعرض أوامر النظام."""
    embed = discord.Embed(
        title="📜 أوامر البوت",
        description="هذي الأوامر المتاحة لجميع الأعضاء.",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="👥 أوامر عامة",
        value=(
            "• `$help` : عرض هذه القائمة\n"
            "• `$userinfo [@عضو]` : عرض معلومات الحساب\n"
            "• `$serverinfo` : عرض معلومات السيرفر\n"
            "• `$avatar [@عضو]` : عرض صورة الحساب"
        ),
        inline=False
    )
    embed.set_footer(text="لأوامر الإدارة الكاملة راسل الأدمن.")
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
# 🛡️ أوامر النظام المجنونة -- حصرياً للأدمنية فقط
# ==========================================

@bot.command(name='adminhelp', aliases=['نظام'])
@commands.has_role(ADMIN_ROLE_ID)
async def adminhelp(ctx):
    """قائمة كاملة بكل أوامر الإدارة الخارقة."""
    embed = discord.Embed(
        title="🛡️ أوامر النظام الإدارية الخارقة",
        description="هذي الأوامر محصورة على الأدمنية فقط ولا يمكن للأعضاء استخدامها.",
        color=discord.Color.red()
    )
    embed.add_field(
        name="👤 إدارة الأعضاء والعقوبات",
        value=(
            "• `$رول @عضو @رتبة` : سحب أو إعطاء رتبة\n"
            "• `$انقلع @عضو [السبب]` : طرد عضو\n"
            "• `$ختفو @عضو [السبب]` : حظر عضو\n"
            "• `$timeout @عضو <دقائق> [السبب]` : تايم آوت مؤقت\n"
            "• `$untimeout @عضو` : إلغاء التايم آوت\n"
            "• `$اسم @عضو <الاسم الجديد>` : تغيير نك نيم عضو\n"
            "• `$warn @عضو <سبب>` : تسجيل تحذير لعضو\n"
            "• `$warnings @عضو` : عرض تحذيرات عضو\n"
            "• `$clearwarns @عضو` : تصفية تحذيرات عضو"
        ),
        inline=False
    )
    embed.add_field(
        name="💬 إدارة الرومات والرتب (مع صنع الرتب)",
        value=(
            "• `$صنع_رتبة <الاسم>` (أو `$createrole`) : صنع رتبة جديدة بالعربي/الإنجليزي\n"
            "• `$حذف_رتبة <الرتبة>` (أو `$deleterole`) : حذف رتبة من السيرفر\n"
            "• `$صنع_روم <اسم>` (أو `$createchannel`) : صنع روم كتابي جديد\n"
            "• `$حذف_روم <الروم>` (أو `$deletechannel`) : حذف روم\n"
            "• `$مسح <عدد>` : مسح الرسائل\n"
            "• `$قفل` / `$فتح` : قفل أو فتح الروم\n"
            "• `$سلومود <ثواني>` : الوضع البطيء"
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ مزايا إضافية للأدمن",
        value=(
            "• `$ping` : فحص سرعة البوت\n"
            "• `$botstats` : حالة البوت والتشغيل\n"
            "• `$rolelist` : قائمة الرتب والأعضاء فيها"
        ),
        inline=False
    )
    await ctx.reply(embed=embed, mention_author=True)


@bot.command(name='role', aliases=['رول'])
@commands.has_role(ADMIN_ROLE_ID)
async def role_toggle(ctx, member: discord.Member, role: discord.Role):
    try:
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.reply(f"🧹 تم سحب رتبة **{role.name}** من العضو {member.mention} بنجاح!", mention_author=True)
        else:
            await member.add_roles(role)
            await ctx.reply(f"✅ تم إعطاء رتبة **{role.name}** للعضو {member.mention} بنجاح!", mention_author=True)
    except Exception:
        await ctx.reply("❌ تعذر تنفيذ الأمر. تأكد من صلاحيات البوت وأن رتبته أعلى من الرتبة المطلوبة.", mention_author=True)


@bot.command(aliases=['انقلع'])
@commands.has_role(ADMIN_ROLE_ID)
async def kick(ctx, member: discord.Member, *, reason: str = "لم يتم ذكر سبب"):
    try:
        await member.kick(reason=reason)
        await ctx.reply(f"👞 تم طرد العضو {member.mention} من السيرفر. السبب: `{reason}`", mention_author=True)
    except Exception:
        await ctx.reply("❌ تعذر طرد العضو. تأكد من أن رتبة البوت أعلى من العضو.", mention_author=True)


@bot.command(aliases=['ختفو'])
@commands.has_role(ADMIN_ROLE_ID)
async def ban(ctx, member: discord.Member, *, reason: str = "لم يتم ذكر سبب"):
    try:
        await member.ban(reason=reason)
        await ctx.reply(f"🔨 تم حظر العضو {member.mention} من السيرفر. السبب: `{reason}`", mention_author=True)
    except Exception:
        await ctx.reply("❌ تعذر حظر العضو. تأكد من صلاحيات البوت.", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason: str = "لم يتم ذكر سبب"):
    try:
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await ctx.reply(f"⏱️ تم إعطاء {member.mention} تايم آوت لمدة **{minutes} دقيقة**. السبب: `{reason}`", mention_author=True)
    except Exception as e:
        await ctx.reply(f"❌ تعذر تنفيذ التايم آوت: `{e}`", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def untimeout(ctx, member: discord.Member):
    try:
        await member.timeout(None)
        await ctx.reply(f"✅ تم إلغاء التايم آوت عن {member.mention}.", mention_author=True)
    except Exception as e:
        await ctx.reply(f"❌ تعذر إلغاء التايم آوت: `{e}`", mention_author=True)


@bot.command(aliases=['اسم'])
@commands.has_role(ADMIN_ROLE_ID)
async def nickname(ctx, member: discord.Member, *, new_name: str):
    try:
        await member.edit(nick=new_name)
        await ctx.reply(f"✏️ تم تغيير اسم {member.mention} إلى **{new_name}**.", mention_author=True)
    except Exception as e:
        await ctx.reply(f"❌ تعذر تغيير الاسم: `{e}`", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def warn(ctx, member: discord.Member, *, reason: str = "لم يتم ذكر سبب"):
    warnings_log.setdefault(member.id, []).append({
        "reason": reason,
        "by": ctx.author.display_name,
    })
    count = len(warnings_log[member.id])
    await ctx.reply(f"⚠️ تم تحذير {member.mention} (تحذير رقم {count}). السبب: `{reason}`", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def warnings(ctx, member: discord.Member):
    entries = warnings_log.get(member.id, [])
    if not entries:
        await ctx.reply(f"ℹ️ ما فيه تحذيرات مسجلة لـ {member.mention}.", mention_author=True)
        return
    listing = "\n".join(f"{i+1}. {e['reason']} — بواسطة {e['by']}" for i, e in enumerate(entries))
    embed = discord.Embed(title=f"⚠️ تحذيرات {member.display_name}", description=listing, color=discord.Color.orange())
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def clearwarns(ctx, member: discord.Member):
    if member.id in warnings_log:
        warnings_log[member.id] = []
        await ctx.reply(f"🧹 تم تصفية ومسح جميع تحذيرات العضو {member.mention} بنجاح!", mention_author=True)
    else:
        await ctx.reply(f"ℹ️ العضو {member.mention} ليس لديه أي تحذيرات أصلًا.", mention_author=True)


# ==========================================
# 🛠️ أوامر صنع الرتب والرومات للأدمنية
# ==========================================

@bot.command(name='صنع_رتبة', aliases=['createrole'])
@commands.has_role(ADMIN_ROLE_ID)
async def create_role(ctx, *, role_name: str):
    try:
        guild = ctx.guild
        new_role = await guild.create_role(name=role_name, reason=f"أنشئت بواسطة {ctx.author}")
        await ctx.reply(f"✨ تم صنع الرتبة بنجاح: {new_role.mention} (الاسم: `{role_name}`)", mention_author=True)
    except Exception as e:
        await ctx.reply(f"❌ حدث خطأ أثناء صنع الرتبة: `{e}`", mention_author=True)


@bot.command(name='حذف_رتبة', aliases=['deleterole'])
@commands.has_role(ADMIN_ROLE_ID)
async def delete_role(ctx, role: discord.Role):
    try:
        role_name = role.name
        await role.delete(reason=f"حذفت بواسطة {ctx.author}")
        await ctx.reply(f"🗑️ تم حذف الرتبة **{role_name}** بنجاح!", mention_author=True)
    except Exception as e:
        await ctx.reply(f"❌ تعذر حذف الرتبة: `{e}`", mention_author=True)


@bot.command(name='صنع_روم', aliases=['createchannel'])
@commands.has_role(ADMIN_ROLE_ID)
async def create_channel(ctx, *, channel_name: str):
    try:
        guild = ctx.guild
        new_channel = await guild.create_text_channel(name=channel_name)
        await ctx.reply(f"📢 تم إنشاء الروم الكتابي بنجاح: {new_channel.mention}", mention_author=True)
    except Exception as e:
        await ctx.reply(f"❌ حدث خطأ أثناء إنشاء الروم: `{e}`", mention_author=True)


@bot.command(name='حذف_روم', aliases=['deletechannel'])
@commands.has_role(ADMIN_ROLE_ID)
async def delete_channel(ctx, channel: discord.TextChannel = None):
    target_channel = channel or ctx.channel
    try:
        await target_channel.delete(reason=f"حذف بواسطة {ctx.author}")
    except Exception as e:
        await ctx.reply(f"❌ تعذر حذف الروم: `{e}`", mention_author=True)


@bot.command(aliases=['مسح'])
@commands.has_role(ADMIN_ROLE_ID)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسالة يا {ctx.author.mention}!", delete_after=3)


@bot.command(aliases=['قفل'])
@commands.has_role(ADMIN_ROLE_ID)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.reply("🔒 تم قفل الروم عن الجميع بنجاح!", mention_author=True)


@bot.command(aliases=['فتح'])
@commands.has_role(ADMIN_ROLE_ID)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.reply("🔓 تم فك قفل الروم وإتاحته للجميع!", mention_author=True)


@bot.command(aliases=['سلومود'])
@commands.has_role(ADMIN_ROLE_ID)
async def slowmode(ctx, seconds: int = 0):
    await ctx.channel.edit(slowmode_delay=seconds)
    if seconds == 0:
        await ctx.reply("🐇 تم إيقاف الوضع البطيء.", mention_author=True)
    else:
        await ctx.reply(f"🐢 تم تفعيل الوضع البطيء: رسالة كل **{seconds}** ثانية.", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def rolelist(ctx):
    roles = [r for r in ctx.guild.roles if r.name != "@everyone"]
    roles.sort(key=lambda r: r.position, reverse=True)
    listing = "\n".join(f"{r.mention} — {len(r.members)} عضو" for r in roles) or "ما فيه رتب."
    embed = discord.Embed(title=f"📋 رتب سيرفر {ctx.guild.name}", description=listing, color=discord.Color.purple())
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def ping(ctx):
    await ctx.reply(f"🏓 شغال ياحلو! سرعة الاستجابة: **{round(bot.latency * 1000)}ms**", mention_author=True)


@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def botstats(ctx):
    uptime_seconds = int(time.time() - BOT_START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    embed = discord.Embed(title="⚙️ حالة البوت", color=discord.Color.green())
    embed.add_field(name="⏱️ مدة التشغيل", value=f"{hours}س {minutes}د {seconds}ث", inline=True)
    embed.add_field(name="🌐 عدد السيرفرات", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="📶 البينق", value=f"{round(bot.latency * 1000)}ms", inline=True)
    await ctx.reply(embed=embed, mention_author=True)


# ==========================================
# 🛑 معالجة الأخطاء
# ==========================================

@role_toggle.error
@kick.error
@ban.error
@timeout.error
@untimeout.error
@nickname.error
@warn.error
@warnings.error
@clearwarns.error
@create_role.error
@delete_role.error
@create_channel.error
@delete_channel.error
@ping.error
@clear.error
@lock.error
@unlock.error
@slowmode.error
@rolelist.error
@botstats.error
@adminhelp.error
async def admin_commands_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.reply("❌ عذراً، هذا الأمر مخصص للإدارة العليا فقط! الأعضاء العاديين ما لهم حق.", mention_author=True)
    else:
        raise error


@bot.event
async def on_ready():
    print(f"✅ تم تشغيل بوت النظام الإداري بنجاح: {bot.user}")


# تشغيل خادم الويب للحفاظ على الاتصال 24/7
keep_alive()

bot.run(os.environ.get("DISCORD_TOKEN"))
