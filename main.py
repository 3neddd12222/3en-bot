import os
import time
from datetime import timedelta
import discord
from discord.ext import commands

# --- إعدادات الـ Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)

ADMIN_ROLE_ID = 1544759188289359944
BOT_START_TIME = time.time()
warnings_log: dict[int, list[dict]] = {}

@bot.event
async def on_ready():
    print(f"✅ تم تشغيل البوت بنجاح: {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

# ==========================================
# 📢 أوامر العامة
# ==========================================

@bot.command(name='help')
async def help_cmd(ctx):
    embed = discord.Embed(title="📜 أوامر البوت", color=discord.Color.blue())
    embed.add_field(
        name="👥 أوامر عامة",
        value="• `$help` : القائمة\n• `$userinfo` : معلومات الحساب\n• `$serverinfo` : معلومات السيرفر\n• `$avatar` : صورة الحساب",
        inline=False
    )
    await ctx.reply(embed=embed, mention_author=True)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"👤 معلومات - {member.name}", color=discord.Color.gold())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="الاسم:", value=member.mention, inline=True)
    embed.add_field(name="الـ ID:", value=f"`{member.id}`", inline=True)
    await ctx.reply(embed=embed, mention_author=True)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=f"🏰 سيرفر - {guild.name}", color=discord.Color.purple())
    embed.add_field(name="الأعضاء:", value=f"👥 {guild.member_count}", inline=True)
    await ctx.reply(embed=embed, mention_author=True)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"🖼️ صورة {member.name}", color=discord.Color.blue())
    embed.set_image(url=member.display_avatar.url)
    await ctx.reply(embed=embed, mention_author=True)

# ==========================================
# 🛡️ أوامر الإدارة
# ==========================================

@bot.command(name='adminhelp')
@commands.has_role(ADMIN_ROLE_ID)
async def adminhelp(ctx):
    embed = discord.Embed(title="🛡️ أوامر الإدارة", color=discord.Color.red())
    embed.add_field(
        name="التحكم",
        value="• `$رول` • `$انقلع` • `$ختفو` • `$timeout` • `$untimeout` • `$مسح` • `$قفل` • `$فتح` • `$ping`",
        inline=False
    )
    await ctx.reply(embed=embed, mention_author=True)

@bot.command(name='role', aliases=['رول'])
@commands.has_role(ADMIN_ROLE_ID)
async def role_toggle(ctx, member: discord.Member, role: discord.Role):
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.reply(f"🧹 تم سحب رتبة **{role.name}**!", mention_author=True)
    else:
        await member.add_roles(role)
        await ctx.reply(f"✅ تم إعطاء رتبة **{role.name}**!", mention_author=True)

@bot.command(aliases=['انقلع'])
@commands.has_role(ADMIN_ROLE_ID)
async def kick(ctx, member: discord.Member, *, reason: str = "بدون سبب"):
    await member.kick(reason=reason)
    await ctx.reply(f"👞 تم طرد {member.mention}.", mention_author=True)

@bot.command(aliases=['ختفو'])
@commands.has_role(ADMIN_ROLE_ID)
async def ban(ctx, member: discord.Member, *, reason: str = "بدون سبب"):
    await member.ban(reason=reason)
    await ctx.reply(f"🔨 تم حظر {member.mention}.", mention_author=True)

@bot.command(aliases=['مسح'])
@commands.has_role(ADMIN_ROLE_ID)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 تم مسح {amount} رسالة!", delete_after=3)

@bot.command(aliases=['قفل'])
@commands.has_role(ADMIN_ROLE_ID)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.reply("🔒 تم قفل الروم!", mention_author=True)

@bot.command(aliases=['فتح'])
@commands.has_role(ADMIN_ROLE_ID)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.reply("🔓 تم فتح الروم!", mention_author=True)

@bot.command()
@commands.has_role(ADMIN_ROLE_ID)
async def ping(ctx):
    await ctx.reply(f"🏓 الاستجابة: **{round(bot.latency * 1000)}ms**", mention_author=True)

# --- التشغيل ---
if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ لم يتم العثور على DISCORD_TOKEN في Environment Variables!")
