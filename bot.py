import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio

intents = discord.Intents.default()
intents.guilds = True
intents.guild_messages = True
intents.message_content = True
intents.members = True
client = commands.Bot(command_prefix="/", intents=intents)

# Variáveis de controle e armazenamento
guild_configs = {}
bids = {}
alt_bids = {}
bot_ready = False

@client.event
async def on_ready():
    global bot_ready
    bot_ready = True
    await client.tree.sync()
    print(f"Bot online como {client.user}")

@client.event
async def on_guild_join(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(
                """
Olá! Eu sou o bot de gerenciamento de bids.

Para começar, quem adicionou o bot deve seguir os passos:
1. Use /bidadm para definir quem poderá administrar o bot.
2. Use /bidmember para definir quem poderá usar o comando /bid.
3. Use /bidchannel para definir onde os bids serão exibidos.
4. Use /bidstart para liberar o funcionamento do bot.

Depois disso, os membros com permissão poderão usar:
- /bid VALOR para registrar seus lances com o personagem principal
- /bidalt VALOR CLAN para registrar bids com personagem alt (ex: /bidalt 5M Omega)

Admins também poderão usar:
- /bidtotal para ver o total acumulado
- /bidmembros para listar quem participou
- /bidstop para zerar os dados
- /bidreset para redefinir tudo e começar do zero
"""
            )
            break

# Comando: /bidadm
@client.tree.command(name="bidadm")
@app_commands.describe(role="Mencione o cargo que será o administrador do bot")
async def bidadm(interaction: discord.Interaction, role: discord.Role):
    _check_admin(interaction)
    _get_config(interaction.guild_id)["admin_role"] = role.id
    await interaction.response.send_message(f"Cargo admin definido com sucesso: {role.mention}")

# Comando: /bidmember
@client.tree.command(name="bidmember")
@app_commands.describe(role="Mencione o cargo que poderá usar o comando /bid")
async def bidmember(interaction: discord.Interaction, role: discord.Role):
    _check_admin(interaction)
    _get_config(interaction.guild_id)["member_role"] = role.id
    await interaction.response.send_message(f"Cargo de membros definido com sucesso: {role.mention}")

# Comando: /bidchannel
@client.tree.command(name="bidchannel")
@app_commands.describe(channel="Canal onde os bids serão exibidos")
async def bidchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    _check_admin(interaction)
    _get_config(interaction.guild_id)["channel_id"] = channel.id
    await interaction.response.send_message(f"Canal de operação definido com sucesso: {channel.mention}")

# Comando: /bidstart
@client.tree.command(name="bidstart")
async def bidstart(interaction: discord.Interaction):
    _check_admin(interaction)
    config = _get_config(interaction.guild_id)
    if not all([config.get("admin_role"), config.get("member_role"), config.get("channel_id")]):
        await interaction.response.send_message("Defina todos os campos (/bidadm, /bidmember, /bidchannel) antes de iniciar.", ephemeral=True)
        return
    config["started"] = True
    await interaction.response.send_message("Bot liberado com sucesso. Agora aceitando bids.")

# Comando: /bid
@client.tree.command(name="bid")
@app_commands.describe(valor="Informe o valor do bid (ex: 10M)")
async def bid(interaction: discord.Interaction, valor: str):
    config = _get_config(interaction.guild_id)
    if not config.get("started"):
        await interaction.response.send_message("O bot ainda não foi iniciado com /bidstart.", ephemeral=True)
        return
    if not _has_role(interaction.user, config.get("member_role")):
        await interaction.response.send_message("Você não tem permissão para dar bid.", ephemeral=True)
        return
    if interaction.user.id in bids or interaction.user.id in alt_bids:
        await interaction.response.send_message("Você já enviou um bid. Aguarde a próxima rodada.", ephemeral=True)
        return
    bids[interaction.user.id] = valor
    canal = client.get_channel(config["channel_id"])
    await canal.send(f"{interaction.user.mention} - {valor}")
    await interaction.response.send_message("Seu bid foi registrado com sucesso.", ephemeral=True)

# Comando: /bidalt
@client.tree.command(name="bidalt")
@app_commands.describe(valor="Informe o valor do bid (ex: 5M)", clan="Nome do clã com o qual está participando")
async def bidalt(interaction: discord.Interaction, valor: str, clan: str):
    config = _get_config(interaction.guild_id)
    if not config.get("started"):
        await interaction.response.send_message("O bot ainda não foi iniciado com /bidstart.", ephemeral=True)
        return
    if not _has_role(interaction.user, config.get("member_role")):
        await interaction.response.send_message("Você não tem permissão para dar bid.", ephemeral=True)
        return
    if interaction.user.id in bids or interaction.user.id in alt_bids:
        await interaction.response.send_message("Você já enviou um bid. Aguarde a próxima rodada.", ephemeral=True)
        return
    alt_bids[interaction.user.id] = (valor, clan)
    canal = client.get_channel(config["channel_id"])
    await canal.send(f"{interaction.user.mention} - {valor} - ALT na {clan}")
    await interaction.response.send_message("Seu bid (ALT) foi registrado com sucesso.", ephemeral=True)

# Comando: /bidtotal
@client.tree.command(name="bidtotal")
async def bidtotal(interaction: discord.Interaction):
    _check_admin(interaction)
    total = sum(_parse_valor(v) for v in bids.values()) + sum(_parse_valor(v[0]) for v in alt_bids.values())
    await interaction.response.send_message(f"Total em bids: {total:,.0f} gold")

# Comando: /bidmembros
@client.tree.command(name="bidmembros")
async def bidmembros(interaction: discord.Interaction):
    _check_admin(interaction)
    nomes = [f"<@{uid}>" for uid in bids.keys()] + [f"<@{uid}> (ALT)" for uid in alt_bids.keys()]
    await interaction.response.send_message("Membros que deram bid:\n" + "\n".join(nomes))

# Comando: /bidstop
@client.tree.command(name="bidstop")
async def bidstop(interaction: discord.Interaction):
    _check_admin(interaction)
    bids.clear()
    alt_bids.clear()
    await interaction.response.send_message("Todos os bids foram zerados com sucesso.")

# Comando: /bidreset
@client.tree.command(name="bidreset")
async def bidreset(interaction: discord.Interaction):
    _check_admin(interaction)
    guild_configs.pop(interaction.guild_id, None)
    bids.clear()
    alt_bids.clear()
    await interaction.response.send_message("Todas as configurações e bids foram resetados com sucesso.")

# Funções auxiliares
def _get_config(guild_id):
    if guild_id not in guild_configs:
        guild_configs[guild_id] = {}
    return guild_configs[guild_id]

def _check_admin(interaction):
    config = _get_config(interaction.guild_id)
    admin_id = config.get("admin_role")
    if not admin_id or not _has_role(interaction.user, admin_id):
        raise app_commands.errors.CheckFailure("Você não tem permissão para isso.")

def _has_role(user, role_id):
    return any(role.id == role_id for role in user.roles)

def _parse_valor(valor):
    valor = valor.strip().upper()
    try:
        if valor.endswith("M"):
            return float(valor[:-1]) * 1_000_000
        elif valor.endswith("K"):
            return float(valor[:-1]) * 1_000
        return float(valor)
    except:
        return 0

from aiohttp import web
import threading

async def handle(request):
    return web.Response(text="Bot rodando.")

def start_webserver():
    app = web.Application()
    app.router.add_get('/', handle)
    web.run_app(app, port=3000)

threading.Thread(target=start_webserver).start()


client.run(os.environ['YOUR_BOT_TOKEN'])
