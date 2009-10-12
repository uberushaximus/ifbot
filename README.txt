
ifbot requires Python 2.6, but does not work on Python 3.x.

Run ifbot.py to run the program, but you'll first need some
patched interpreters and a configuration file named ifbot.cfg

See sample.cfg for a sample configuration file. You will probably
want to change the server and channel that the bot joins.

You will need patched interpreters to run. The way I created mine
was largely a nonrepeatable process. Hopefully I'll have better
instructions in the future. For now, try the instructions for
Meldrew, at http://icculus.org/meldrew/


It works best to stick the compiled interpreters in the main folder,
and then add a new line for them in the configuration file. The sample
one looks like this at the current time:

[dumbfrotz]
ext=.z1;.z2;.z3;.z4;.z5;.z6;.z7;.z8
command=dumbfrotz -w 120 {file}

The name of the interpreter is dumbfrotz. It automatically recognizes
the extensions .z1, .z2, etc. And when invoked it runs the command
"dumbfrotz -w 120 {file}" where {file} will be replaced by the filename.

The bot sends commands to stdin, and reads them from stdout, spewing them
into the channel. For that reason, the bot should not be used in a popular
channel, and may be kicked for flooding. There are configuration options
to control the minimum delay between messages and characters. The default
rates are a bit slow, so you may need to change the numbers.


To issue commands to the bot, simply address him via commands like:

ifbot: load http://mirror.ifarchive.org/if-archive/games/zcode/curses.z5

alternately, you may whisper the commands. The full list of commands is
available by sending the bot the message "help"

To play a game, prefix your command with a greater-than sign (>). This
helps to distinguish it from normal chat.


At the time of writing, there are a number of bugs and quirks, and
development is fairly slow, as I have other projects. If you'd like to
contribute, send an email to nagelbagel@gmail.com
