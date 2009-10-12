
import ConfigParser as configparser
import os, subprocess, sys, threading, time, traceback
import urllib2, urllib

from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower, ip_numstr_to_quad, ip_quad_to_numstr

STORYFILE_SUB = "{file}"

class RejoinExit(BaseException):
    """An exception that indicates the bot should rejoin."""

def readconfig(files, silent=True):
    
    settings = {
        'nickname': 'ifbot',
        'server': 'irc.darkmyst.org',
        'port': 6667,
        'channel': '#ifbot',
        'charrate': .003, # seconds to sleep per char
        'msgrate': .2, # seconds to sleep per message
        'maxstorysize': 2 * 1024 * 1024, # Maximum file size
    }
    
    IRC = 'irc'
    
    config = configparser.SafeConfigParser()
    config.read(files)
    if config.has_section(IRC):
        for key, value in settings.items():
            if config.has_option(IRC, key):
                try:
                    settings[key] = type(value)(config.get(IRC, key))
                except TypeError:
                    pass
    
    EXTENSIONS = 'ext'
    COMMAND = 'command'
    
    terps = {}
    terp_exts = {}
    
    for section in config.sections():
        if section == IRC:
            continue
        
        if not config.has_option(section, COMMAND):
            if not silent:
                print("Config: Missing '{command}' for {section}.".format(
                    command=COMMAND, section=section))
            continue
        command = config.get(section, COMMAND)
        if STORYFILE_SUB not in command:
            if not silent:
                print("Config: No '{replacement}' in '{command}' for {section}.".format(
                    replacement=STORYFILE_SUB, command=COMMAND, section=section))
            continue
        
        terps[section] = command
        
        if not config.has_option(section, EXTENSIONS):
            if not silent:
                print("Config: Missing '{exts}' for {section}.".format(exts=EXTENSIONS, section=section))
            continue
        extlist = config.get(section, EXTENSIONS).strip().split(';')
        extlist = [ext.strip() for ext in extlist]
        for ext in extlist:
            if not ext:
                continue
            if ext[0] != '.':
                ext = '.' + ext
            if '.' in ext[1:]:
                if not silent:
                    print("Config: Extra period in extension '{ext}' for {section}.".format(
                        ext=ext, section=section))
                continue
            if ext in terp_exts:
                section2 = terp_exts[ext]
                if not silent:
                    if section == section2:
                        print("Config: Duplicate extension '{ext}' in {section}.".format(
                            ext=ext, section=section))
                    else:
                        print("Config: Duplicate extension '{ext}' in {section1} and {section2}.".format(
                            ext=ext, section1=section2, section2=section))
                continue
            terp_exts[ext] = section
    return settings, terps, terp_exts

def simplify(path):
    """Simplifies a uri."""
    unused, tail = os.path.split(path)
    return os.path.join('games', tail)

class InteractiveBot(SingleServerIRCBot):
    """
    A simple bot that runs interactive fiction collaboratively.
    
    Based on Meldrew.
    """
    
    def __init__(self, configs, join=True):
        """Initializes the bot."""
        self.settings, self.terps, self.terp_exts = readconfig(configs, silent=False)
        if not self.terps:
            print("No interpreters specified in configuration. Add to {file}.".format(file=" ".join(configs)))
            sys.exit(1)
        SingleServerIRCBot.__init__(self, [[self.settings['server'], self.settings['port']]], self.settings['nickname'], self.settings['nickname'])
        self.immediate_join = join
        
        self.process = None
        self.thread = None
        self.lock = threading.Lock()
        self.buffer = []
    
    @property
    def channel(self):
        """The channel the bot should join."""
        return self.settings['channel']
    
    @property
    def nickname(self):
        """The channel the bot should join."""
        return self.settings['nickname']
    
    @property
    def rates(self):
        """Max characters per second and max messages per second."""
        return self.settings['charrate'], self.settings['msgrate']
    
    @property
    def maxsize(self):
        """Max story size."""
        return self.settings['maxstorysize']
    
    def on_nicknameinuse(self, c, e):
        c.nick(c.get_nickname() + "_")

    def on_welcome(self, c, e):
        if self.immediate_join:
            c.join(self.channel)
            c.privmsg(self.channel, "Helloooooooooooooooooo!")

    def on_privmsg(self, c, e):
        nick = nm_to_n(e.source())
        c = self.connection
        if nick == c.get_nickname():
            return
        self.do_command(e, e.arguments()[0])

    def on_pubmsg(self, c, e):
        nick = nm_to_n(e.source())
        c = self.connection
        if nick == c.get_nickname():
            return
        a = e.arguments()[0].split(":", 1)
        if len(a) > 1 and irc_lower(a[0]) == irc_lower(self.connection.get_nickname()):
            self.do_command(e, a[1].strip())
        else:
            cmd = e.arguments()[0]
            if cmd[0] == '>':
                self.interpret(e, cmd[1:])
    
    def download_game(self, nick, uri, localpath):
        c = self.connection
        request = urllib2.Request(uri)
        if request.get_type() == 'http':
            headrequest = urllib2.Request(uri)
            # HACK: Modification of request object
            headrequest.get_method = lambda: "HEAD"
            rec = urllib2.urlopen(headrequest)
            head = rec.info()
            #print rec, head
            #if head.status > 200 or head.status <= 300:
            #    c.notice(nick, "The specified game URI '{uri}' returned "
            #        "status code {code}.".format(uri=uri, code=head.status))
            #    return
            try:
                length = int(head.getheader('Content-Length', 0))
            except:
                length = 0
            if length == 0:
                c.notice(nick, "The specified game URI '{uri}' returned "
                    "no data.".format(uri=uri))
                return
            elif length > self.maxsize:
                c.notice(nick, "The specified game '{uri}' is too large; "
                    "{actual}KiB when the max is {max}KiB.".format(
                    uri=uri, actual=length/1024, max=self.maxsize/1024))
                return
        #elif request.get_type() == 'ftp':
        #    pass
        else:
            c.notice(nick, "The specified game URI {uri} has "
                "a disallowed scheme {scheme}.".format(
                    uri=uri, scheme=request.type))
            return
        
        unused, headers = urllib.urlretrieve(uri, localpath)
        #if headers.status < 200 or headers.status >= 300:
        #    c.notice(nick, "The specified game URI '{uri}' returned "
        #        "status code {code}.".format(uri=uri, code=head.status))
        #    return
    
    def do_command(self, e, cmd):
        nick = nm_to_n(e.source())
        c = self.connection
        print("{nick}: {cmd}".format(nick=nick, cmd=cmd))
        
        input = cmd
        args = cmd.split()
        cmd = args[0]
        args = [irc_lower(arg) for arg in args]
        cmd = irc_lower(cmd)
        
        #if cmd in ("disconnect", "die"):
        #    sys.exit(1)
        if cmd in ("exit", "quit"):
            if self.process:
                self.kill_game()
                c.privmsg(self.channel, '{nick} has quit the current game.'.format(nick=nick))
            else:
                c.notice(nick, 'No game is currently active.')
            return
        elif cmd in ("reset", "restart", "reboot", "rejoin"):
            raise RejoinExit("Restarting the client...")
        elif cmd in ('play', 'load', 'start', 'create', 'open', 'run'):
            if self.process:
                c.notice(nick, 'You cannot start a new game until you have quit the current one.')
                return
            if len(args) < 2:
                c.notice(nick, "You must specify a game to play.")
                return
            
            terp = None
            if len(args) > 2:
                if args[1] in self.terps:
                    terp = self.terps[args[1]]
                    game = input.split(None, 2)[2]
            if terp is None:
                unused, game = input.split(None, 1)
                unused, ext = os.path.splitext(game)
                if ext not in self.terp_exts:
                    c.notice(nick, "The '{ext}' extension is unknown; "
                    "first specify the interpreter to use '{name}: start [interpreter] [game]' "
                    "to try to run this game.".format(ext=ext, name=self.nickname))
                    return
                terp = self.terps[self.terp_exts[ext]]
            
            #game = urllib.quote(game)
            gamepath = simplify(game)
            gameroot, unused = os.path.splitext(gamepath)
            unused, gamepath = os.path.split(gamepath)
            gamepath = os.path.join(gameroot, gamepath)
            if not os.path.exists(gamepath):
                try:
                    os.makedirs(gameroot)
                except:
                    pass
                
                try:
                    file = self.download_game(nick, game, gamepath)
                    if file is None:
                        return
                except Exception:
                    print("Exception occurred during download.")
                    traceback.print_exc(file=sys.stdout)
                    c.notice(nick, "Could not find the specified game '{uri}'.".format(uri=game))
                    return
            
            if not os.path.exists(gamepath) or not os.path.exists(gameroot):
                c.notice(nick, "Error accessing downloaded file for game '{uri}'.".format(uri=game))
                return
            
            unused, gamename = os.path.split(gamepath)
            command = terp.format(file=gamename)
            try:
                self.process = subprocess.Popen(command, bufsize=0,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    #close_fds=True, 
                    cwd=gameroot)
            except Exception as err:
                print("Error starting game.")
                traceback.print_exc(file=sys.stdout)
            if self.process:
                time.sleep(.5)
                self.process.poll()
                if self.process.returncode is not None:
                    self.kill_game()
                    c.notice(nick, "The game loaded but quit immediately.")
                    return
                c.privmsg(self.channel, '{nick} has started the game {game}.'.format(nick=nick, game=gamepath))
                self.thread = threading.Thread(target=self.run_thread, args=[self.process.stdout])
                self.thread.start()
                self.display()
            else:
                c.notice(nick, "An error occurred while starting the game.")
        elif 'terp' in cmd or 'emulator' in cmd:
            c.notice(nick, "Interpreters available:")
            terplist = list(self.terps.keys())
            terplist.sort()
            for item in terplist:
                c.notice(nick, item)
        else:
            c.notice(nick, "{name} plays interactive fiction. "
                    "To start a game, say '{name}: start [interpreter] [uri]', "
                    "where the interpreter is the optional interpreter to specify, "
                    "(otherwise it goes by extension) and "
                    "the uri is the location of the story file, for example".format(name=self.nickname))
            c.notice(nick,
                    "'{name}: start http://mirror.ifarchive.org/if-"
                    "archive/games/zcode/curses.z5'.".format(name=self.nickname))
            c.notice(nick, "Quit the game at any time with '{name}: quit'.".format(name=self.nickname))
            c.notice(nick, "Get a list of interpreters with '{name}: interpreters.".format(name=self.nickname))
            c.notice(nick, "Force this bot to quit and rejoin with '{name}: rejoin'.".format(name=self.nickname))
    
    def interpret(self, e, command):
        nick = nm_to_n(e.source())
        c = self.connection
        if not self.process:
            c.notice(nick, "No game is currently active.")
            return
        if command is not None:
            print("{nick}: >'{command}'".format(nick=nick, command=command))
        self.process.poll()
        if self.process.returncode is not None or not self.thread.isAlive():
            print('quit: process return {code}, thread death {death}'.format(
                code=self.process.returncode, death=self.thread.isAlive()))
            self.kill_game()
            c.privmsg(self.channel, 'The game process has quit.')
            return
        self.process.stdin.write(command + '\n')
        self.process.stdin.flush()
        self.display()
    
    def display(self):
        # Keep displaying until no text left.
        for i in range(4):
            time.sleep(.5)
            c = self.connection
            self.lock.acquire()
            try:
                if len(self.buffer) == 0:
                    continue
                for line in self.buffer:
                    c.privmsg(self.channel, line)
                    time.sleep(self.rates[1] + self.rates[0] * len(line))
                self.buffer = []
            finally:
                self.lock.release()

    def kill_game(self):
        if self.process:
            try:
                self.process.stdout.close()
                self.process.stdin.close()
                self.process.kill()
            except:
                pass
        if self.thread:
            self.thread.join(2)
        self.thread = None
        self.process = None
    
    def run_thread(self, output):
        try:
            while True:
                line = output.readline()
                if len(line) <= 0 or line is None:
                    break
                line = line.strip()
                print(line)
                if len(line) < 5 and len(line) > 0 and (line[0] == '>' or line[0] == '.'):
                    continue
                self.lock.acquire()
                try:
                    self.buffer.append(line)
                finally:
                    self.lock.release()
        except Exception as err:
            print("Unexpected exception.")
            traceback.print_exc(file=sys.stdout)
        output.close()

if __name__ == '__main__':
    join = True
    while True:
        try:
            CONFIG_FILES = ['ifbot.cfg']
            bot = InteractiveBot(CONFIG_FILES, join=join)
            bot.start()
        except RejoinExit as e:
            join = True
            bot.disconnect("Rejoining...")
        except Exception as e:
            join = False
            print("Unexpected exception.")
            traceback.print_exc(file=sys.stdout)
        finally:
            try:
                bot.disconnect()
            except:
                pass
