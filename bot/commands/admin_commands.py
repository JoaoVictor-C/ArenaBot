import os
import discord
from discord.ext.commands import Greedy, Context
from discord import app_commands
from discord.ext import commands
from config import DISCORD_TOKEN
from dotenv import set_key
from typing import Literal, Optional
import config.config as config
import services.riot_api as riot_api  # Importação adicional

class AdminCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    async def admin_check(self, interaction: discord.Interaction) -> bool:
        """Verifica se o usuário tem permissões administrativas."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Você precisa ter permissões de administrador para usar este comando.", ephemeral=True)
            return False
        return True
        
            
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def update_riot_key_prefix(self, ctx, key: str):
        """
        Atualiza a chave da API Riot sem reiniciar o bot.
        
        Uso: !update_riot_key RGAPI-xxxxxxxx-xxxx-xxxx-xxxxxxxxxxxx
        """
        try:
            # Atualiza o valor no arquivo .env
            dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
            set_key(dotenv_path, 'RIOT_API_KEY', key)
            
            # Atualiza o valor em memória
            config.RIOT_API_KEY = key
            riot_api.RIOT_API_KEY = key  # Atualiza também no módulo riot_api
            
            await ctx.send("✅ Chave da API Riot atualizada com sucesso!")
        except Exception as e:
            await ctx.send(f"❌ Erro ao atualizar a chave: {str(e)}")
            
    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def sync(self, ctx: Context, guilds: Greedy[discord.Object], spec: Optional[Literal["~", "*", "^"]] = None) -> None:
        print('Sync command')
        if not guilds:
            if spec == "~":
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "*":
                ctx.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            elif spec == "^":
                # Clear all commands in the guild
                ctx.bot.tree.clear_commands(guild=ctx.guild)
                synced = await ctx.bot.tree.sync(guild=ctx.guild)
            else:
                synced = await ctx.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} commands {'globally' if spec is None else 'to the current guild.'}")
            return

        ret = 0
        for guild in guilds:
            try:
                await ctx.bot.tree.sync(guild=guild)
            except discord.HTTPException:
                pass
            else:
                ret += 1
        await ctx.send(f"Synced the tree to {ret}/{len(guilds)}.")
