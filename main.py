import discord
from discord.ext import commands
from discord.ext import tasks
import requests
import asyncio
import json
import re
from dotenv import load_dotenv
import os

load_dotenv()

intents = discord.Intents.all()
client = commands.Bot(command_prefix = '!', intents=intents)

WeatherAPI_KEY = os.getenv('OpenWeatherMapAPI') #API from https://openweathermap.org/
BOT_TOKEN = os.getenv('DiscordBotToken')

async def get_weather_info(location):
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    
    params = {
        "q": location,
        "appid": WeatherAPI_KEY,
        "units": "metric"
    }
    
    response = requests.get(base_url, params=params)
    
    if response.status_code == 200:
        data = response.json()
        weather_info = {
            "location": f"{data['name']}, {data['sys']['country']}",
            "temperature": data["main"]["temp"],
            "description": data["weather"][0]["description"]
        }
        return weather_info
    else:
        raise Exception(f"Failed to fetch weather information: {response.status_code}")

async def send_weather_update(channel, location):
    weather_info = await get_weather_info(location)
    formatted_weather_info = f"Weather update for {weather_info['location']}:\nTemperature: {weather_info['temperature']}°C\nDescription: {weather_info['description'].capitalize()}"
    await channel.send(formatted_weather_info)

@tasks.loop(hours=1)
async def weather_update_task(channel, location):
    await send_weather_update(channel, location)

async def setup_weather_updates(weather_channel, location, interval):
    weather_update_task.change_interval(hours=interval)
    if not weather_update_task.is_running():
        weather_update_task.start(weather_channel, location)

@client.event
async def on_ready():
    print('Logged in as {0.user}'.format(client))
    print('---------------------------')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    is_allowed_user = 954865029340090449
    is_admin = message.author.guild_permissions.administrator or message.author.id == is_allowed_user

    with open("channels.json", "r") as f:
        data = json.load(f)
        guild_id = str(message.guild.id)
        if guild_id in data:
            channel_id = data[guild_id]
            if is_admin:
                pass
            elif str(message.channel.id) != channel_id:
                channel = client.get_channel(int(channel_id))

                if message.content.startswith('!'):
                    await message.channel.send(f"Sorry, Information Homie has been set to work in {channel.mention} only. Please try again in that channel.")
                    return
        else:
            pass

    await client.process_commands(message)

@client.command()
async def weather(ctx, *, city=None):
    if city is None:
        await ctx.send("What city are you looking for?")
        try:
            message = await client.wait_for('message', timeout=30.0, check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
            city = message.content
        except asyncio.TimeoutError:
            await ctx.send("No city provided. Command cancelled.")
            return
    
    formatted_city = city.lower().replace(" ", "-")
    display_city = city.title()
    
    url = f'http://api.openweathermap.org/data/2.5/weather?q={formatted_city}&units=imperial&appid={WeatherAPI_KEY}'
    response = requests.get(url)

    if response.status_code != 200:
        await ctx.send('Failed to get weather data.')
        return

    data = response.json()

    if data['cod'] == '404':
        await ctx.send('City not found.')
        return
    
    temp = data['main']['temp']
    desc = data['weather'][0]['description']
    await ctx.send(f'The temperature in {display_city} is {temp}°F with {desc}.')

@client.command()
async def setup(ctx):

    is_allowed_user = 954865029340090449
    is_admin = ctx.author.guild_permissions.administrator or ctx.author.id == is_allowed_user

    if not is_admin and ctx.author.id != is_allowed_user:
        await ctx.send("You do not have permission to use this command.")
        return

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    await ctx.send("What would you like to set up? Choose an option:\n1. Set a specific channel for users to use Information Homie in\n2. Set a channel to receive periodic weather updates")

    try:
        option = await client.wait_for('message', check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("Sorry, you took too long to respond.")
        return

    option = option.content.lower()

    if option == "1":
        with open("channels.json", "r") as f:
            channels = json.load(f)

        guild_id = str(ctx.guild.id)
        if guild_id in channels:
            current_channel = client.get_channel(int(channels[guild_id]))
            await ctx.send(f"Information Homie is currently restricted to {current_channel.mention}. Would you like to change it? (yes or no)")
            try:
                response = await client.wait_for('message', check=check, timeout=30.0)
            except asyncio.TimeoutError:
                await ctx.send("Sorry, you took too long to respond.")
                return
            if response.content.lower() != "yes":
                await ctx.send("You didn't respond with `yes` so I have not changed the channel. If you would like to use the command again.")
                return

        await ctx.send("Which channel would you like to restrict bot commands to? (type `remove` to remove the current restriction)")
        try:
            response = await client.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("Sorry, you took too long to respond.")
            return

        channel_id = None
        if response.content.lower() == "remove":
            if guild_id in channels:
                del channels[guild_id]
                with open("channels.json", "w") as f:
                    json.dump(channels, f)
                await ctx.send("Information Homie is no longer restricted to a specific channel.")
            else:
                await ctx.send("Information Homie is not currently restricted to a specific channel.")
            return
        elif len(response.channel_mentions) > 0:
            channel_id = str(response.channel_mentions[0].id)
        elif re.findall(r'<#\d+>', response.content):
            channel_id = re.findall(r'\d+', response.content)[0]

        if not channel_id:
            await ctx.send("Sorry, I could not find a valid channel mention in your message. Please try again.")
            return

        channels[guild_id] = channel_id
        with open("channels.json", "w") as f:
            json.dump(channels, f)

        await ctx.send(f"Information Homie is now restricted to <#{channel_id}>. Don't worry people with `administrator` permissions are still able to freely use the bot in any channel.")

    elif option == "2":
        await ctx.send("Which channel would you like to receive periodic weather updates in? (Mention the channel)")

        try:
            channel_response = await client.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("Sorry, you took too long to respond.")
            return

        if len(channel_response.channel_mentions) == 0:
            await ctx.send("Please mention a valid channel.")
            return

        weather_channel = channel_response.channel_mentions[0]

        await ctx.send("Please provide the location for weather updates (e.g. city name or city name, country code):")

        try:
            location_response = await client.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("Sorry, you took too long to respond.")
            return

        location = location_response.content

        await ctx.send("How often would you like to receive weather updates in this channel? (Enter the number of hours, e.g. `3` for every 3 hours)")

        try:
            interval_response = await client.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("Sorry, you took too long to respond.")
            return

        try:
            interval = int(interval_response.content)
        except ValueError:
            await ctx.send("Invalid input. Please enter a valid number of hours.")
            return

        guild_id = str(ctx.guild.id)
        weather_settings = {
            "channel_id": str(weather_channel.id),
            "location": location,
            "interval": interval
        }

        with open("weatherUpdate.json", "r") as f:
            existing_settings = json.load(f)

        existing_settings[guild_id] = weather_settings

        with open("weatherUpdate.json", "w") as f:
            json.dump(existing_settings, f)

        await ctx.send(f"Weather updates for {location} will be sent to {weather_channel.mention} every {interval} hours.")

    else:
        await ctx.send("Invalid option. We don't have anyother setups available yet, please select between `1` and `2` next time.")

client.run(BOT_TOKEN)