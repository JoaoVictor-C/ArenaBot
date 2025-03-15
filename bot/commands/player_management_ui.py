import discord
from discord.ext import commands
from discord import app_commands
from services.riot_api import verify_riot_id
from database.mongodb_client import get_jogador_by_puuid, add_jogador, update_player_name, get_bot_config, get_jogador_by_riot_id


class CloseMessageView(discord.ui.View):
    def __init__(self, original_message=None):
        super().__init__(timeout=30)
        self.original_message = original_message
    
    async def on_timeout(self):
        # Tentar limpar a mensagem de resposta se ainda existir
        if self.message:
            try:
                await self.message.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

class AddPlayerModal(discord.ui.Modal, title="Adicionar Jogador"):
    riot_id = discord.ui.TextInput(label="Riot ID", placeholder="Nome#TAG", required=True)
    display_name = discord.ui.TextInput(label="Nome", placeholder="Seu nome", required=True, min_length=2, max_length=32)

    def __init__(self, bot, original_message):
        super().__init__()
        self.bot = bot
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        riot_id_input = self.riot_id.value
        nome = self.display_name.value
        print('old riot_id', riot_id_input)
        riot_id_input = riot_id_input.replace(' ', '%20')
        print('new riot_id', riot_id_input)
        

        if '#' not in riot_id_input:
            await interaction.response.send_message("Formato inválido.", ephemeral=True)
            return

        invalid_chars = ['@', '#', ':', '```']
        if any(char in nome for char in invalid_chars):
            await interaction.response.send_message("Caracteres inválidos.", ephemeral=True)
            return
        try:
            name_part, tagline_part = riot_id_input.split('#')
            await interaction.response.defer(ephemeral=True)
            puuid = verify_riot_id(tagline_part, name_part)
            if not puuid:
                await interaction.followup.send(f"❌ Riot ID inválido.", ephemeral=True)
                return
            existing_player = get_jogador_by_puuid(self.bot.db, puuid)
            if existing_player:
                await interaction.followup.send(f"⚠️ Já existe.", ephemeral=True, view=CloseMessageView(self.original_message))
                return
            added = add_jogador(self.bot.db, puuid, riot_id_input, nome, True)
            if added:
                await interaction.followup.send(f"✅ Adicionado.", ephemeral=True, view=CloseMessageView(self.original_message))
            else:
                await interaction.followup.send(f"⚠️ Erro.", ephemeral=True, view=CloseMessageView(self.original_message))
        except ValueError:
            await interaction.followup.send("Formato inválido.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erro: {e}.", ephemeral=True, view=CloseMessageView(self.original_message))
            print(f"Erro: {e}")

class RenamePlayerModal(discord.ui.Modal, title="Alterar Nome"):
    riot_id = discord.ui.TextInput(label="Riot ID", placeholder="Nome#TAG", required=True)
    novo_nome = discord.ui.TextInput(label="Novo Nome", placeholder="Novo nome", required=True, min_length=2, max_length=32)

    def __init__(self, bot, original_message):
        super().__init__()
        self.bot = bot
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        riot_id_input = self.riot_id.value
        novo_nome = self.novo_nome.value
        if '#' not in riot_id_input:
            await interaction.response.send_message("Formato inválido.", ephemeral=True)
            return
        if len(novo_nome) < 2 or len(novo_nome) > 32:
            await interaction.response.send_message("Nome: 2-32 caracteres.", ephemeral=True)
            return
        invalid_chars = ['@', '#', ':', '```']
        if any(char in novo_nome for char in invalid_chars):
            await interaction.response.send_message("Caracteres inválidos.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        name_part, tagline_part = riot_id_input.split('#')
        puuid = verify_riot_id(tagline_part, name_part)
        if not puuid:
            await interaction.followup.send(f"❌ Riot ID inválido.", ephemeral=True, view=CloseMessageView(self.original_message))
            return
        jogador_existente = get_jogador_by_puuid(self.bot.db, puuid)
        if not jogador_existente:
            await interaction.followup.send(f"❌ Não encontrado.", ephemeral=True, view=CloseMessageView(self.original_message))
            return
        if jogador_existente.nome == novo_nome:
            await interaction.followup.send(f"⚠️ Nome igual.", ephemeral=True, view=CloseMessageView(self.original_message))
            return
        view = ConfirmRenameView(self.bot, interaction.user, puuid, novo_nome, jogador_existente.nome, self.original_message)
        await interaction.followup.send(
            content=f"⚠️ Mudar '{jogador_existente.nome}' -> '{novo_nome}'?",
            view=view,
            ephemeral=True
        )

class ConfirmRenameView(discord.ui.View):
    def __init__(self, bot, user, puuid, novo_nome, nome_atual, original_message):
        super().__init__(timeout=60)
        self.bot = bot
        self.user = user
        self.puuid = puuid
        self.novo_nome = novo_nome
        self.nome_atual = nome_atual
        self.original_message = original_message

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("Só quem iniciou pode.", ephemeral=True)
            return
        success = update_player_name(self.bot.db, self.puuid, self.novo_nome)
        for item in self.children:
            item.disabled = True
        if success:
            await interaction.response.edit_message(content=f"✅ '{self.nome_atual}' -> '{self.novo_nome}'!", view=self)
        else:
            await interaction.response.edit_message(content=f"❌ Erro.", view=self)

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message("Só quem iniciou pode.", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="❌ Cancelado.", view=self)

class PlayerManagementView(discord.ui.View):
    """View com botões para gerenciamento"""

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Adicionar Jogador", style=discord.ButtonStyle.green, custom_id="add_player")
    async def add_player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddPlayerModal(self.bot, interaction.message))

    @discord.ui.button(label="Alterar Nome", style=discord.ButtonStyle.blurple, custom_id="rename_player")
    async def rename_player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenamePlayerModal(self.bot, interaction.message))

    @discord.ui.button(label="Informações", style=discord.ButtonStyle.grey, custom_id="info_button")
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        info_text_part1 = (
            "# 🏆 Bem-vindo ao Sistema de Ranqueamento do Arena! 🏆\n\n"
            "Prepare-se para competir e subir nos rankings do nosso modo Arena!  Veja como funciona:\n\n"
            "## 1. Pontuação (`PDL`) 📈\n\n"
            "- Cada jogador tem uma pontuação, chamada `PDL`, que representa sua habilidade.\n"
            "- Você **ganha** `PDL` ao vencer partidas e **perde** ao ser derrotado.\n"
            "- A quantidade de `PDL` ganha ou perdida depende de alguns fatores:\n"
            "    - Sua **colocação** na partida: Quanto melhor você se sair, mais pontos você ganha (ou menos perde).\n"
            "    - A **força dos seus oponentes**: Vencer jogadores com `MMR` mais alto que o seu recompensa mais pontos! 🥇\n"
            "    - Se você é um **novo jogador**: Suas primeiras partidas terão um impacto *maior* no seu `MMR`, para te posicionar mais rapidamente. 🚀\n\n"
            "## 2. Tiers (Elos) 🏅\n\n"
            "Seu `MMR` determina seu **tier** (ou elo), que é uma forma visual de representar sua habilidade.  Temos os seguintes tiers, do menor para o maior:\n\n"
            "-   🟫 Madeira\n"
            "-   ⬜ Prata\n"
            "-   🟨 Ouro\n"
            "-   🟦 Platina\n"
            "-   ⚔️ Gladiador!\n\n"
            "## 3. Atualizações do Ranking 🔄\n\n"
            "- O sistema é atualizado **constantemente**. Isso significa que, após *cada partida*, o `MMR` de todos os jogadores envolvidos é recalculado.\n"
            "- A cada 30 minutos, suas últimas partidas serão adicionadas à sua pontuação. ⏱️\n\n"
        )

        info_text_part2 = (
            "## 4. Adição de Novos Jogadores 🌱\n\n"
            "- Quando você joga o Arena pela primeira vez, o sistema te dará um `MMR` inicial baseado no seu desempenho em outros modos de jogo (se houver dados disponíveis).\n"
            "- As partidas serão contabilizadas *a partir da sua adesão* no nosso sistema, descartando completamente as partidas anteriores.\n"
            "- Se você for um jogador completamente novo, começará com um `MMR` padrão um pouco mais baixo, para ter a chance de aprender e subir!\n\n"
            "## 5. Pontos Importantes ❗\n\n"
            "-   **Seja consistente:** O sistema recompensa jogadores que jogam regularmente e se esforçam para melhorar.\n"
            "-   **Não desanime com derrotas:** Elas fazem parte do aprendizado. Use-as para identificar pontos fracos e evoluir!\n"
            "-   **O sistema é dinâmico:** Ele se ajusta com o tempo, então continue jogando para alcançar seu verdadeiro tier!\n"
            "-   **Anomalias:** O sistema detecta ganhos ou perdas anormais de `MMR`.\n"
            "- **Partidas Recentes**: O sistema busca suas partidas recentes, sempre que você termina uma, para calcular sua nova pontuação com base no MMR médio dos participantes e na sua colocação final.\n\n"
            "---\n\n"
            "Divirta-se e boa sorte na sua jornada rumo ao topo do Arena! 🚀🎉\n\n"
            "> _Desenvolvido por Presente e Crazzyboy_"
        )
        view = CloseMessageView(interaction.message)  # Pass the original message
        await interaction.response.send_message(content=info_text_part1, ephemeral=True)
        await interaction.followup.send(content=info_text_part2, ephemeral=True, view=view)

class PlayerManagementCog(commands.Cog):
    """Sistema de gerenciamento de jogadores via UI interativa"""

    def __init__(self, bot):
        self.bot = bot
        self.setup_message_id = None
        self.setup_channel_id = None
        # Schedule the task to load and setup the UI after the bot is ready
        self.bot.loop.create_task(self.load_and_setup_ui())

    async def load_and_setup_ui(self):
        """Load UI configuration from database and set it up if it exists"""
        await self.bot.wait_until_ready()
        
        try:
            # Load config from the database
            config = get_bot_config(self.bot.db)
            
            if config and "setup_message_id" in config and "setup_channel_id" in config:
                self.setup_message_id = config["setup_message_id"]
                self.setup_channel_id = config["setup_channel_id"]
                
                # Try to fetch the channel and message
                channel = self.bot.get_channel(self.setup_channel_id)
                if channel:
                    try:
                        # Check if the message exists
                        message = await channel.fetch_message(self.setup_message_id)
                        # If we get here, the message exists, but we need to reattach the view
                        view = PlayerManagementView(self.bot)
                        await message.edit(view=view)
                        print(f"Player Management UI reattached to message {self.setup_message_id} in channel {self.setup_channel_id}")
                    except discord.NotFound:
                        # Message was deleted, so we'll need to recreate it
                        print(f"Player Management UI message {self.setup_message_id} not found, will be recreated on next setup")
                        self.setup_message_id = None
                else:
                    print(f"Channel {self.setup_channel_id} not found")
        except Exception as e:
            print(f"Error loading Player Management UI configuration: {e}")

    def save_config(self):
        """Save the current UI configuration to the database"""
        try:
            config = get_bot_config(self.bot.db) or {}
            config["setup_message_id"] = self.setup_message_id
            config["setup_channel_id"] = self.setup_channel_id
            config["config_id"] = 1  # Ensure config_id is set for upserts
            
            # Update the config in the database
            settings_collection = self.bot.db.get_collection('bot_settings')
            settings_collection.update_one(
                {"config_id": 1},
                {"$set": config},
                upsert=True
            )
            print(f"Player Management UI configuration saved: message_id={self.setup_message_id}, channel_id={self.setup_channel_id}")
        except Exception as e:
            print(f"Error saving Player Management UI configuration: {e}")

    @commands.command(name="adicionar_ui")
    @commands.has_permissions(administrator=True)
    async def adicionar_ui(self, ctx, channel: discord.TextChannel = None):
        """
        Comando para configurar o painel de gerenciamento.
        Requer permissões de administrador.
        """
        channel = channel or ctx.channel
        self.setup_channel_id = channel.id
        
        # Check if UI is already set up
        if self.setup_message_id and self.setup_channel_id:
            try:
                old_channel = self.bot.get_channel(self.setup_channel_id)
                await old_channel.fetch_message(self.setup_message_id)
                await ctx.send("A UI já está configurada!", delete_after=10)
                await ctx.message.delete()
                return  # Exit if UI exists
            except discord.NotFound:
                pass  # Message deleted, proceed to create
            except Exception as e:
                print(f"Erro ao verificar: {e}")
                #  Still proceed, in case of other errors

        # Create the embed
        embed = discord.Embed(
            title="🏆 Sistema de Gerenciamento de Jogadores",
            description="Use os botões abaixo...",
            color=0x3498db
        )
        embed.add_field(name="Adicionar Jogador", value="Registre-se.", inline=False)
        embed.add_field(name="Alterar Nome", value="Atualize.", inline=False)
        embed.add_field(name="Informações", value="Saiba como.", inline=False)
        embed.set_footer(text="Sistema por Presente e Crazzyboy")
        
        # Define a imagem de fundo
        background_image_url = "https://trackercdn.com/ghost/images/2023/7/7920_arena-league-of-legends-map.png"
        
        # Criar um embed com a imagem de fundo
        embed.set_image(url=background_image_url)

        view = PlayerManagementView(self.bot)
        setup_message = await channel.send(embed=embed, view=view)

        self.setup_message_id = setup_message.id
        self.setup_channel_id = channel.id
        
        # Save configuration to database
        self.save_config()
        
        try:
            await ctx.message.delete()  # Delete the command message
        except Exception as e:
            print(f"Erro ao apagar: {e}")
            
    
    @app_commands.command(name="pdl", description="Verifica PDL de um jogador")
    async def pdl(self, interaction: discord.Interaction, player_identifier: str):
        """Verifica PDL de um jogador usando slash command"""
        await interaction.response.defer(ephemeral=True)

        pdl = await self.get_player_pdl(player_identifier)

        if pdl is not None:
            await interaction.followup.send(
                f"O PDL de {player_identifier} é: **{pdl}**",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Jogador '{player_identifier}' não encontrado.",
                ephemeral=True
            )

    async def get_player_pdl(self, player_identifier: str) -> int:
        """
        Obtém o PDL de um jogador específico usando nome ou Riot ID no mesmo argumento.
        Formato de Riot ID: "PlayerName#Tag"
        """
        # Se contiver '#', tratamos como Riot ID; caso contrário, como nome simples
        if '#' in player_identifier:
            try:
                name_part, tagline_part = player_identifier.split('#', 1)
                name_part = name_part.replace('%20', ' ')
                puuid = verify_riot_id(tagline_part, name_part)
                if not puuid:
                    return None
                player = get_jogador_by_puuid(self.bot.db, puuid)
            except Exception:
                return None
        else:
           # player = get_jogador_by_nome(self.bot.db, player_identifier)
            return None

        if player is None:
            return None

        return getattr(player, 'mmr_atual', None)  # Ajuste a propriedade conforme necessário