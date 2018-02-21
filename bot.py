import discord
from discord.ext import commands
from discord.voice_client import VoiceClient



if not discord.opus.is_loaded():
    # the 'opus' library here is opus.dll on windows
    # or libopus.so on linux in the current directory
    # you should replace this with the location the
    # opus library is located in and with the proper filename.
    # note that on windows this DLL is automatically provided for you
    discord.opus.load_opus('opus')

def __init__(self, bot):
        self.bot = bot

class VoiceEntry:
    def __init__(self, message, player):
        self.requester = message.author
        self.channel = message.channel
        self.player = player

    def __str__(self):
        fmt = ' {0.title} uploaded by {0.uploader} and requested by {1.display_name}'
        duration = self.player.duration
        if duration:
            fmt = fmt + ' [length: {0[0]}m {0[1]}s]'.format(divmod(duration, 60))
        return fmt.format(self.player, self.requester)

class VoiceState:
    def __init__(self, bot):
        self.current = None
        self.voice = None
        self.bot = bot
        self.play_next_song = asyncio.Event()
        self.songs = asyncio.Queue()
        self.skip_votes = set() # a set of user_ids that voted
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        if self.voice is None or self.current is None:
            return False

        player = self.current.player
        return not player.is_done()

    @property
    def player(self):
        return self.current.player

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing():
            self.player.stop()

    def toggle_next(self):
        self.bot.loop.call_soon_threadsafe(self.play_next_song.set)

    async def audio_player_task(self):
        while True:
            self.play_next_song.clear()
            self.current = await self.songs.get()
            await self.bot.send_message(self.current.channel, 'En train de jouer' + str(self.current))
            self.current.player.start()
            await self.play_next_song.wait()
class Music:
    """Commandes liées à la voix.
    Fonctionne sur plusieurs serveurs à la fois.
    """
    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    def get_voice_state(self, server):
        state = self.voice_states.get(server.id)
        if state is None:
            state = VoiceState(self.bot)
            self.voice_states[server.id] = state

        return state

    async def create_voice_client(self, channel):
        voice = await self.bot.join_voice_channel(channel)
        state = self.get_voice_state(channel.server)
        state.voice = voice

    def __unload(self):
        for state in self.voice_states.values():
            try:
                state.audio_player.cancel()
                if state.voice:
                    self.bot.loop.create_task(state.voice.disconnect())
            except:
                pass

    @commands.command(pass_context=True, no_pm=True)
    async def join(self, ctx, *, channel : discord.Channel):
        """Se joint à un canal vocal."""
        try:
            await self.create_voice_client(channel)
        except discord.ClientException:
            await self.bot.say('Déjà dans un canal vocal ...')
        except discord.InvalidArgument:
            await self.bot.say('Ce n"est pas un canal vocal ...')
        else:
            await self.bot.say('Prêt à lire le son en **' + channel.name)

    @commands.command(pass_context=True, no_pm=True)
    async def summon(self, ctx):
        """Invoque le bot pour rejoindre votre salon."""
        summoned_channel = ctx.message.author.voice_channel
        if summoned_channel is None:
            await self.bot.say('T"es sur que t"es dans un channel ?')
            return False

        state = self.get_voice_state(ctx.message.server)
        if state.voice is None:
            state.voice = await self.bot.join_voice_channel(summoned_channel)
        else:
            await state.voice.move_to(summoned_channel)

        return True

    @commands.command(pass_context=True, no_pm=True)
    async def play(self, ctx, *, song : str):
        """Joue un son
        """
        state = self.get_voice_state(ctx.message.server)
        opts = {
            'default_search': 'auto',
            'quiet': True,
        }

        if state.voice is None:
            success = await ctx.invoke(self.summon)
            await self.bot.say("Le son charge wala..")
            if not success:
                return

        try:
            player = await state.voice.create_ytdl_player(song, ytdl_options=opts, after=state.toggle_next)
        except Exception as e:
            fmt = 'Une erreur est survenue lors du traitement de cette requête: ```py\n{}: {}\n```'
            await self.bot.send_message(ctx.message.channel, fmt.format(type(e).__name__, e))
        else:
            player.volume = 0.6
            entry = VoiceEntry(ctx.message, player)
            await self.bot.say('Enqueued ' + str(entry))
            await state.songs.put(entry)

    @commands.command(pass_context=True, no_pm=True)
    async def volume(self, ctx, value : int):
        """Règle le volume de la chanson en cours de lecture"""

        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.volume = value / 100
            await self.bot.say('Met le volume à {:.0%}'.format(player.volume))
    @commands.command(pass_context=True, no_pm=True)
    async def resume(self, ctx):
        """Remet le son"""
        state = self.get_voice_state(ctx.message.server)
        if state.is_playing():
            player = state.player
            player.resume()

    @commands.command(pass_context=True, no_pm=True)
    async def stop(self, ctx):
        """Arrete le son et vire le bot du salon
        """
        server = ctx.message.server
        state = self.get_voice_state(server)

        if state.is_playing():
            player = state.player
            player.stop()

        try:
            state.audio_player.cancel()
            del self.voice_states[server.id]
            await state.voice.disconnect()
            await self.bot.say("Le son à été arreter et le bot viré")
        except:
            pass

    @commands.command(pass_context=True, no_pm=True)
    async def skip(self, ctx):
        """Votez pour sauter une chanson. Le demandeur de chanson peut sauter automatiquement.
        3 votes par sauts sont nécessaires pour que la chanson soit sautée.
        """

        state = self.get_voice_state(ctx.message.server)
        if not state.is_playing():
            await self.bot.say('Ne joue pas de musique actuellement')
            return

        voter = ctx.message.author
        if voter == state.current.requester:
            await self.bot.say('Demande de saut du son')
            state.skip()
        elif voter.id not in state.skip_votes:
            state.skip_votes.add(voter.id)
            total_votes = len(state.skip_votes)
            if total_votes >= 3:
                await self.bot.say('Allez on saute ton son il pue la mort')
                state.skip()
            else:
                await self.bot.say('Passage de vote ajouté, actuellement à [{} / 3]'.format(total_votes))
        else:
            await self.bot.say('T"as déja voté frero')

    @commands.command(pass_context=True, no_pm=True)
    async def playing(self, ctx):
        """Affiche des informations sur le son"""

        state = self.get_voice_state(ctx.message.server)
        if state.current is None:
            await self.bot.say('Ne joue rien.')
        else:
            skip_count = len(state.skip_votes)
            await self.bot.say('En train de jouer {} [skips: {}/3]'.format(state.current, skip_count))
            
def setup(bot):
    bot.add_cog(Music(bot))
    print('Le son charge')
startup_extensions =["Music"]
bot = commands.Bot("!")

@bot.event
async def on_ready():
    print("bot online")

class Main_Commands():
    def __init__(self, bot):
        self.bot = bot

@bot.command(pass_context=True)
async def ping(ctx):
    await bot.say("ntm")


@bot.command(pass_context=True)
async def hello(ctx):
    await bot.say("hi :wave:")


if __name__ == "__main__":
    for extension in startup_extensions:
        try:
            bot.load_extension(extension)
        except Exception as e:
                exc = '{}:{}'.format(type(e).__name__,e)
                print('Echec lors du chargement de l"extention {}\n{}'.format(extension, exc))


bot.run("NDE1NDE1NDQyNTgwOTYzMzI5.DW4OLg.sZsP_smDBTybp-X4H6KBbBQp_sM")
