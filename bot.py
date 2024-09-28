import os
import discord
from discord.ext import commands, tasks
import yt_dlp as youtube_dl
import asyncio
from myserver import server_on

# ตั้งค่า yt-dlp สำหรับการดึงข้อมูลเพลง
ตัวเลือก_ytdl = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'verbose': True
}

ตัวเลือก_ffmpeg = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ตัวเลือก_ytdl)

# คลาสสำหรับการจัดการเพลงจาก URL
class แหล่งที่มา_YTDL(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.thumbnail = data.get('thumbnail')  # เก็บภาพปกเพลง
        self.uploader = data.get('uploader')    # เก็บชื่อศิลปิน
        self.duration = data.get('duration')    # เก็บความยาวเพลง

    @classmethod
    async def จาก_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ตัวเลือก_ffmpeg), data=data)

# คลาสสำหรับคำสั่งเพลงทั้งหมด
class เพลง(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.คิวเพลง = []  # คิวเพลงที่กำลังรอเล่น
        self.ผู้เล่นปัจจุบัน = None
        self.ตรวจสอบการออกจากห้อง.start()  # เริ่มงานตรวจสอบการออกจากห้อง

    @commands.command(name="เล่น", help="🎶 เล่นเพลงจาก URL หรือชื่อเพลงที่ระบุ")
    async def เล่น(self, ctx, *, url):
        async with ctx.typing():
            ผู้เล่น = await แหล่งที่มา_YTDL.จาก_url(url, loop=self.bot.loop, stream=True)
            ctx.voice_client.play(ผู้เล่น, after=lambda e: print(f'ข้อผิดพลาด: {e}') if e else self.เล่นเพลงถัดไป(ctx))
            self.ผู้เล่นปัจจุบัน = ผู้เล่น

            embed = discord.Embed(
                title=f"🎵 กำลังเล่นเพลง: {ผู้เล่น.title}",
                description=f"🎤 ศิลปิน: {ผู้เล่น.uploader}",
                color=discord.Color.purple()
            )
            embed.add_field(name="📅 เพลงถัดไป", value="ไม่มีเพลงถัดไป" if not self.คิวเพลง else self.คิวเพลง[0].title, inline=False)
            embed.add_field(name="🎧 ช่องเพลง", value=ctx.voice_client.channel.name, inline=True)
            embed.add_field(name="⏲️ เวลาเพลง", value=f"{ผู้เล่น.duration // 60} นาที {ผู้เล่น.duration % 60} วินาที", inline=True)
            embed.set_image(url=ผู้เล่น.thumbnail)  # แสดงภาพปกเพลงในขนาดใหญ่

            view = ปุ่มควบคุมเพลง(self)
            await ctx.send(embed=embed, view=view)

    async def หยุดชั่วคราว(self, interaction):
        if interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("⏸️ หยุดเล่นเพลงชั่วคราว", ephemeral=True)

    async def เล่นต่อ(self, interaction):
        if interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("▶️ เล่นเพลงต่อ", ephemeral=True)

    async def หยุด(self, interaction):
        interaction.guild.voice_client.stop()
        self.คิวเพลง.clear()
        await interaction.response.send_message("⏹️ หยุดเล่นเพลงและเคลียร์คิว", ephemeral=True)

    async def ข้าม(self, interaction):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏭️ ข้ามเพลง", ephemeral=True)

    async def ออกจากห้อง(self, interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 บอทออกจากห้องแล้ว", ephemeral=True)
        else:
            await interaction.response.send_message("🚫 บอทไม่อยู่ในห้องเสียง", ephemeral=True)

    async def คิวเพลง(self, interaction):
        if len(self.คิวเพลง) > 0:
            รายการคิว = "\n".join([f"{idx+1}. {song.title}" for idx, song in enumerate(self.คิวเพลง)])
            embed = discord.Embed(title="🎶 คิวเพลงปัจจุบัน", description=รายการคิว, color=discord.Color.green())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("📜 ไม่มีเพลงในคิว", ephemeral=True)

    def เล่นเพลงถัดไป(self, ctx):
        if len(self.คิวเพลง) > 0:
            เพลงถัดไป = self.คิวเพลง.pop(0)
            ctx.voice_client.play(เพลงถัดไป, after=lambda e: self.เล่นเพลงถัดไป(ctx))
            self.ผู้เล่นปัจจุบัน = เพลงถัดไป
        else:
            self.ผู้เล่นปัจจุบัน = None

    @tasks.loop(minutes=1.0)
    async def ตรวจสอบการออกจากห้อง(self):
        for vc in self.bot.voice_clients:
            if not vc.is_playing() and len(vc.channel.members) == 1:
                await vc.disconnect()

    @ตรวจสอบการออกจากห้อง.before_loop
    async def ก่อนตรวจสอบการออกจากห้อง(self):
        await self.bot.wait_until_ready()

    @เล่น.before_invoke
    async def ตรวจสอบเสียง(self, ctx):
        if ctx.voice_client is None:
            await ctx.author.voice.channel.connect()
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @commands.command(name="สถานะ", help="📜 ตั้งสถานะของบอท")
    async def สถานะ(self, ctx, *, status_message):
        await self.bot.change_presence(activity=discord.Game(name=status_message))
        await ctx.send(f"📜 ตั้งสถานะเป็น: {status_message}")

    @commands.command(name="ข้อมูล", help="📊 แสดงข้อมูลบอท")
    async def ข้อมูล(self, ctx):
        embed = discord.Embed(
            title="📊 ข้อมูลของบอท",
            description=(
                f"**ชื่อบอท:** {self.bot.user.name}\n\n"
                f"**ID:** {self.bot.user.id}\n\n"
                f"**จำนวนเซิร์ฟเวอร์:** {len(self.bot.guilds)}\n\n"
                f"**จำนวนผู้ใช้:** {len(set(self.bot.get_all_members()))}\n\n"
                "🌟 ขอบคุณที่ใช้บริการบอทของเรา! 🌟"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="เครดิต: white_286", icon_url="https://example.com/credit_icon.png")  # ใส่เครดิตผู้สร้าง
        await ctx.send(embed=embed)

class ปุ่มควบคุมเพลง(discord.ui.View):
    def __init__(self, เพลง: เพลง):
        super().__init__(timeout=None)
        self.เพลง = เพลง

    @discord.ui.button(label="⏸️ หยุดชั่วคราว", style=discord.ButtonStyle.primary, custom_id="หยุดชั่วคราว")
    async def หยุดชั่วคราว(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.เพลง.หยุดชั่วคราว(interaction)

    @discord.ui.button(label="▶️ เล่นต่อ", style=discord.ButtonStyle.primary, custom_id="เล่นต่อ")
    async def เล่นต่อ(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.เพลง.เล่นต่อ(interaction)

    @discord.ui.button(label="⏹️ หยุด", style=discord.ButtonStyle.danger, custom_id="หยุด")
    async def หยุด(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.เพลง.หยุด(interaction)

    @discord.ui.button(label="⏭️ ข้าม", style=discord.ButtonStyle.secondary, custom_id="ข้าม")
    async def ข้าม(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.เพลง.ข้าม(interaction)

    @discord.ui.button(label="👋 ออกจากห้อง", style=discord.ButtonStyle.danger, custom_id="ออกจากห้อง")
    async def ออกจากห้อง(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.เพลง.ออกจากห้อง(interaction)

    @discord.ui.button(label="📜 คิวเพลง", style=discord.ButtonStyle.secondary, custom_id="คิวเพลง")
    async def คิวเพลง(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.เพลง.คิวเพลง(interaction)

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

@bot.event
async def on_ready():
    print(f'เข้าสู่ระบบในชื่อ {bot.user.name}')
    # ส่งข้อความแนะนำการใช้บอทไปยังช่องที่บอทเข้าร่วม
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name='general')  # เปลี่ยน 'general' เป็นชื่อช่องที่ต้องการ
        if channel:
            await channel.send(
                "👋 สวัสดี! ฉันเป็นบอทเพลงของคุณ! นี่คือคำสั่งที่คุณสามารถใช้:\n"
                "`!เล่น [URL/ชื่อเพลง]`: เล่นเพลงจาก URL หรือชื่อเพลง\n"
                "`⏸️ หยุดชั่วคราว`: หยุดเพลงชั่วคราว\n"
                "`▶️ เล่นต่อ`: เล่นเพลงที่หยุดชั่วคราว\n"
                "`⏹️ หยุด`: หยุดเพลงและเคลียร์คิว\n"
                "`⏭️ ข้าม`: ข้ามเพลงปัจจุบัน\n"
                "`👋 ออกจากห้อง`: ออกจากห้องเสียง\n"
                "`📜 คิวเพลง`: แสดงคิวเพลงปัจจุบัน\n"
                "`!สถานะ [ข้อความ]`: ตั้งสถานะของบอท\n"
                "`!ข้อมูล`: แสดงข้อมูลของบอท"
            )

server_on()

async def main():
    async with bot:
        await bot.add_cog(เพลง(bot))
        await bot.start(os.getenv('TOKEN'))  # เปลี่ยนเป็น token ของบอทคุณเอง

# เริ่มต้น event loop
asyncio.run(main())
