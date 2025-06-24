import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import asyncio
import os
from aiohttp import web
import threading

intents = discord.Intents.default()
client = commands.Bot(command_prefix="/", intents=intents)

bot_config = {}
bid_data = {}

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    try:
        for guild in client.guilds:
            await client.tree.sync(guild=guild)
        print("Comandos sincronizados com sucesso.")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

def _get_config(guild_id):
    if guild_id not in bot_config:
        bot_config[guild_id] = {
            "admin_role": None,
            "member_role": None,
            "channel_id": None,
            "active": False
        }
    return bot_config[guild_id]

def _check_admin(interaction):
    config = _get_config(interaction.guild_id)
    if config["admin_role"] is None or config["admin_role"] not in [role.id for role in interaction.user.roles]:
        raise app_commands.errors.CheckFailure("Você não tem permissão para isso.")

def _has_role(interaction, role_id):
    return role_id in [role.id for role in interaction.user.roles]

@client.tree.command(name="bidadm")
@app_commands.describe(role="Mencione o cargo que será o administrador do bot")
async def bidadm(interaction: discord.Interaction, role: discord.Role):
    config = _get_config(interaction.guild_id)
    config["admin_role"] = role.id
    await interaction.response.send_message(f"Cargo admin definido com sucesso: {role.mention}")

@client.tree.command(name="bidmember")
@app_commands.describe(role="Mencione o cargo que poderá utilizar o comando /bid")
async def bidmember(interaction: discord.Interaction, role: discord.Role):
    _check_admin(interaction)
    config = _get_config(interaction.guild_id)
    config["member_role"] = role.id
    await interaction.response.send_message(f"Cargo de membro definido com sucesso: {role.mention}")

@client.tree.command(name="bidchannel")
@app_commands.describe(channel="Canal onde o bot irá operar")
async def bidchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    _check_admin(interaction)
    config = _get_config(interaction.guild_id)
    config["channel_id"] = channel.id
    await interaction.response.send_message(f"Canal definido com sucesso: {channel.mention}")

@client.tree.command(name="bidstart")
async def bidstart(interaction: discord.Interaction):
    _check_admin(interaction)
    config = _get_config(interaction.guild_id)
    config["active"] = True
    bid_data[interaction.guild_id] = {
        "main": {},
        "alts": []
    }
    await interaction.response.send_message("Bot liberado para receber bids.")

@client.tree.command(name="bid")
@app_commands.guild_only()
@app_commands.describe(valor="Valor de gold disponível para bid. Ex: 10M")
async def bid(interaction: discord.Interaction, valor: str):
    config = _get_config(interaction.guild_id)
    if not config["active"]:
        await interaction.response.send_message("O bot ainda não está ativo para receber bids.", ephemeral=True)
        return
    if not _has_role(interaction, config["member_role"]):
        await interaction.response.send_message("Você não tem permissão para usar este comando.", ephemeral=True)
        return
    user_id = interaction.user.id
    if user_id in bid_data[interaction.guild_id]["main"]:
        await interaction.response.send_message("Você já enviou um bid.", ephemeral=True)
        return
    bid_data[interaction.guild_id]["main"][user_id] = valor
    channel = client.get_channel(config["channel_id"])
    await channel.send(f"{interaction.user.mention} - {valor}")
    await interaction.response.send_message("Bid registrado com sucesso.", ephemeral=True)

@client.tree.command(name="bidalt")
@app_commands.guild_only()
@app_commands.describe(valor="Valor de gold do alt. Ex: 10M", clan="Nome do clan do alt")
async def bidalt(interaction: discord.Interaction, valor: str, clan: str):
    config = _get_config(interaction.guild_id)
    if not config["active"]:
        await interaction.response.send_message("O bot ainda não está ativo para receber bids.", ephemeral=True)
        return
    if not _has_role(interaction, config["member_role"]):
        await interaction.response.send_message("Você não tem permissão para usar este comando.", ephemeral=True)
        return
    user_id = interaction.user.id
    for entry in bid_data[interaction.guild_id]["alts"]:
        if entry["user"] == user_id:
            await interaction.response.send_message("Você já enviou um bid com alt.", ephemeral=True)
            return
    bid_data[interaction.guild_id]["alts"].append({"user": user_id, "valor": valor, "clan": clan})
    channel = client.get_channel(config["channel_id"])
    await channel.send(f"{interaction.user.mention} - {valor} - ALT na {clan}")
    await interaction.response.send_message("Bid de alt registrado com sucesso.", ephemeral=True)

@client.tree.command(name="bidtotal")
async def bidtotal(interaction: discord.Interaction):
    _check_admin(interaction)
    data = bid_data.get(interaction.guild_id, {"main": {}, "alts": []})
    total_main = sum(int(v.replace("M", "")) for v in data["main"].values())

    clan_totals = {}
    for alt in data["alts"]:
        valor = int(alt["valor"].replace("M", ""))
        clan = alt["clan"]
        if clan not in clan_totals:
            clan_totals[clan] = 0
        clan_totals[clan] += valor

    msg = f"Total em bids MAIN: {total_main}M\n"
    for clan, total in clan_totals.items():
        msg += f"Total em bids ALT [{clan}]: {total}M\n"
    await interaction.response.send_message(msg)

@client.tree.command(name="bidmembros")
async def bidmembros(interaction: discord.Interaction):
    _check_admin(interaction)
    data = bid_data.get(interaction.guild_id, {"main": {}, "alts": []})
    membros_main = [f"<@{uid}>" for uid in data["main"].keys()]
    membros_alt = [f"<@{alt['user']}> ({alt['clan']})" for alt in data["alts"]]
    msg = "Membros com bid MAIN:\n" + ", ".join(membros_main) + "\n\nMembros com bid ALT:\n" + ", ".join(membros_alt)
    await interaction.response.send_message(msg)

@client.tree.command(name="bidstop")
async def bidstop(interaction: discord.Interaction):
    _check_admin(interaction)
    bid_data[interaction.guild_id] = {"main": {}, "alts": []}
    await interaction.response.send_message("Todos os bids foram apagados.")

@client.tree.command(name="bidreset")
async def bidreset(interaction: discord.Interaction):
    _check_admin(interaction)
    bot_config[interaction.guild_id] = {
        "admin_role": None,
        "member_role": None,
        "channel_id": None,
        "active": False
    }
    bid_data[interaction.guild_id] = {"main": {}, "alts": []}
    await interaction.response.send_message("Bot resetado. Por favor, reconfigure as permissões e canal.")

@client.event
async def on_guild_join(guild):
    default_channel = None
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            default_channel = channel
            break
    if default_channel:
        await default_channel.send(
            "Olá! Eu sou o NCBid Bot.\n\n"
            "Antes de começar a usar, um administrador precisa configurar as permissões.\n\n"
            "1. Use `/bidadm` para definir o cargo de administradores.\n"
            "2. Use `/bidmember` para definir o cargo de membros que podem dar bid.\n"
            "3. Use `/bidchannel` para escolher o canal onde o bot vai operar.\n"
            "4. Use `/bidstart` para liberar os comandos de bid.\n"
            "5. Membros podem usar `/bid` ou `/bidalt`.\n\n"
            "Admins podem usar `/bidtotal`, `/bidmembros`, `/bidstop` e `/bidreset`."
        )

# Webserver para manter o Render "acordado"
async def handle(request):
    return web.Response(text="Bot está rodando!")

def start_webserver():
    app = web.Application()
    app.router.add_get('/', handle)

    runner = web.AppRunner(app)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 3000)
        await site.start()

    loop.run_until_complete(run())
    loop.run_forever()

# Iniciar webserver em thread separada
threading.Thread(target=start_webserver).start()

client.run(os.environ['YOUR_BOT_TOKEN'])
