
.. _cli:

###
CLI
###

The library comes with a CLI tool called ``rctclient`` that offers some useful subcommands.

The tools require the  `click <https://click.palletsprojects.com/>`_ module and won't work without it. If installing
via `pip`, the requirement can be pulled in by specifying ``rctclient[cli]``.

For certain parameters, the tool supports shell completion. Read more about this at the `click documentation
<https://click.palletsprojects.com/en/7.x/bashcomplete/#activation>`_. For Bash, the completion can be activated using
the following command: ``eval "$(_RCTCLIENT_COMPLETE=source_bash rctclient)"``

.. click:: rctclient.cli:cli
   :prog: rctclient
   :nested: full
