import discord
from discord.ext import commands
import sqlite3
import json
import datetime
import colorama
from colorama import Fore, Back, Style

# Initialize colorama
colorama.init(autoreset=True)

# Create Discord bot with necessary intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Database setup
def setup_database():
    print(f"{Fore.CYAN}[DATABASE] {Fore.WHITE}Setting up database...")
    conn = sqlite3.connect('server_backup.db')
    c = conn.cursor()
    
    # Create tables for server, channels, roles, and permissions
    c.execute('''CREATE TABLE IF NOT EXISTS servers
                 (server_id TEXT PRIMARY KEY, name TEXT, backup_date TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS channels
                 (channel_id TEXT PRIMARY KEY, server_id TEXT, name TEXT, type TEXT, 
                  position INTEGER, category_id TEXT, permissions TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS roles
                 (role_id TEXT PRIMARY KEY, server_id TEXT, name TEXT, color INTEGER,
                  permissions TEXT, position INTEGER, hoist BOOLEAN, mentionable BOOLEAN)''')
    
    conn.commit()
    conn.close()
    print(f"{Fore.CYAN}[DATABASE] {Fore.GREEN}Database setup complete!")

@bot.event
async def on_ready():
    print(f"{Fore.YELLOW}╔══════════════════════════════════════╗")
    print(f"{Fore.YELLOW}║ {Fore.GREEN}Bot is now online and ready!{Fore.YELLOW}         ║")
    print(f"{Fore.YELLOW}║ {Fore.BLUE}Logged in as: {Fore.WHITE}{bot.user}{Fore.YELLOW}     ║")
    print(f"{Fore.YELLOW}║ {Fore.BLUE}Bot ID: {Fore.WHITE}{bot.user.id}{Fore.YELLOW}          ║")
    print(f"{Fore.YELLOW}╚══════════════════════════════════════╝")
    setup_database()

@bot.command()
async def backup(ctx):
    try:
        print(f"{Fore.CYAN}[BACKUP] {Fore.WHITE}Starting backup for server: {Fore.YELLOW}{ctx.guild.name}")
        guild = ctx.guild
        conn = sqlite3.connect('server_backup.db')
        c = conn.cursor()
        
        # Backup server info
        backup_date = datetime.datetime.now().isoformat()
        c.execute("INSERT OR REPLACE INTO servers VALUES (?, ?, ?)",
                 (str(guild.id), guild.name, backup_date))
        print(f"{Fore.CYAN}[BACKUP] {Fore.WHITE}Server info backed up")
        
        # Backup channels
        for channel in guild.channels:
            overwrites = {}
            for target, overwrite in channel.overwrites.items():
                overwrites[str(target.id)] = {
                    'allow': overwrite.pair()[0].value,
                    'deny': overwrite.pair()[1].value
                }
            
            c.execute("INSERT OR REPLACE INTO channels VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (str(channel.id), str(guild.id), channel.name,
                      str(channel.type), channel.position,
                      str(channel.category_id) if channel.category_id else None,
                      json.dumps(overwrites)))
        print(f"{Fore.CYAN}[BACKUP] {Fore.WHITE}Channels backed up")
        
        # Backup roles
        for role in guild.roles:
            c.execute("INSERT OR REPLACE INTO roles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (str(role.id), str(guild.id), role.name, role.color.value,
                      str(role.permissions.value), role.position,
                      role.hoist, role.mentionable))
        print(f"{Fore.CYAN}[BACKUP] {Fore.WHITE}Roles backed up")
        
        conn.commit()
        conn.close()
        
        print(f"{Fore.CYAN}[BACKUP] {Fore.GREEN}Backup completed successfully!")
        await ctx.send(f"Server backup completed successfully! Backup date: {backup_date}")
        
    except Exception as e:
        print(f"{Fore.RED}[ERROR] {Fore.WHITE}Backup failed: {e}")
        await ctx.send(f"Error during backup: {e}")

@bot.command()
async def restore(ctx, backup_server_id: str):
    try:
        print(f"{Fore.MAGENTA}[RESTORE] {Fore.WHITE}Starting restore for server: {Fore.YELLOW}{ctx.guild.name}")
        guild = ctx.guild
        conn = sqlite3.connect('server_backup.db')
        c = conn.cursor()
        
        # Verify backup exists
        c.execute("SELECT * FROM servers WHERE server_id = ?", (backup_server_id,))
        if not c.fetchone():
            print(f"{Fore.RED}[ERROR] {Fore.WHITE}No backup found for server ID: {backup_server_id}")
            await ctx.send("No backup found for the specified server ID!")
            return
        
        # Restore roles
        print(f"{Fore.MAGENTA}[RESTORE] {Fore.WHITE}Restoring roles...")
        c.execute("SELECT * FROM roles WHERE server_id = ? ORDER BY position", (backup_server_id,))
        roles_data = c.fetchall()
        for role_data in roles_data:
            try:
                await guild.create_role(
                    name=role_data[2],
                    color=discord.Color(role_data[3]),
                    permissions=discord.Permissions(int(role_data[4])),
                    hoist=role_data[6],
                    mentionable=role_data[7]
                )
                print(f"{Fore.MAGENTA}[RESTORE] {Fore.WHITE}Role restored: {role_data[2]}")
            except Exception as e:
                print(f"{Fore.RED}[ERROR] {Fore.WHITE}Error restoring role {role_data[2]}: {e}")
        
        # Restore channels
        print(f"{Fore.MAGENTA}[RESTORE] {Fore.WHITE}Restoring channels...")
        c.execute("SELECT * FROM channels WHERE server_id = ? ORDER BY position", (backup_server_id,))
        channels_data = c.fetchall()
        for channel_data in channels_data:
            try:
                overwrites = json.loads(channel_data[6])
                channel_overwrites = {}
                for target_id, perms in overwrites.items():
                    role = discord.utils.get(guild.roles, id=int(target_id))
                    if role:
                        channel_overwrites[role] = discord.PermissionOverwrite.from_pair(
                            discord.Permissions(perms['allow']),
                            discord.Permissions(perms['deny'])
                        )
                
                if channel_data[3] == 'category':
                    await guild.create_category(
                        name=channel_data[2],
                        overwrites=channel_overwrites,
                        position=channel_data[4]
                    )
                elif channel_data[3] == 'text':
                    await guild.create_text_channel(
                        name=channel_data[2],
                        overwrites=channel_overwrites,
                        position=channel_data[4],
                        category=discord.utils.get(guild.categories, id=int(channel_data[5])) if channel_data[5] else None
                    )
                elif channel_data[3] == 'voice':
                    await guild.create_voice_channel(
                        name=channel_data[2],
                        overwrites=channel_overwrites,
                        position=channel_data[4],
                        category=discord.utils.get(guild.categories, id=int(channel_data[5])) if channel_data[5] else None
                    )
                print(f"{Fore.MAGENTA}[RESTORE] {Fore.WHITE}Channel restored: {channel_data[2]}")
            except Exception as e:
                print(f"{Fore.RED}[ERROR] {Fore.WHITE}Error restoring channel {channel_data[2]}: {e}")
        
        conn.close()
        print(f"{Fore.MAGENTA}[RESTORE] {Fore.GREEN}Restore completed successfully!")
        await ctx.send("Server restore completed successfully!")
        
    except Exception as e:
        print(f"{Fore.RED}[ERROR] {Fore.WHITE}Restore failed: {e}")
        await ctx.send(f"Error during restore: {e}")

# Run the bot
bot.run("YOUR TOKEN")