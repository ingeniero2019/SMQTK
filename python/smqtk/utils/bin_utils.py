import argparse
import json
import logging
import logging.handlers
import os
import time

from . import configuration


__author__ = "paul.tunison@kitware.com"


def initialize_logging(logger, stream_level=logging.WARNING,
                       output_filepath=None, file_level=None):
    """
    Standard logging initialization.

    :param logger: Logger instance to initialize
    :type logger: logging.Logger

    :param stream_level: Logging level to set for the stderr stream formatter.
    :type stream_level: int

    :param output_filepath: Output logging from the given logger to the provided
        file path. Currently, we log to that file indefinitely, i.e. no
        rollover. Rollover may be added in the future if the need arises.
    :type output_filepath: str

    :param file_level: Logging level to output to the file. This the same as the
        stream level by default.

    """
    log_formatter = logging.Formatter(
        "%(levelname)7s - %(asctime)s - %(name)s.%(funcName)s - %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    stream_handler.setLevel(stream_level)
    logger.addHandler(stream_handler)

    if output_filepath:
        # TODO: Setup rotating part of the handler?
        file_handler = logging.handlers.RotatingFileHandler(output_filepath,
                                                            mode='w',
                                                            delay=1)
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(file_level or stream_level)
        logger.addHandler(file_handler)

    # Because there are two levels checked before a logging message is emitted:
    #   * the logging object's level
    #   * The stream handlers level
    logger.setLevel(min(stream_level, file_level or stream_level))


def load_config(config_path, defaults=None):
    """
    Load the JSON configuration dictionary from the specified filepath.

    If the given path does not point to a valid file, we return an empty
    dictionary or the default dictionary if one was provided, returning False
    as our second return argument.

    :param config_path: Path to the (valid) JSON configuration file.
    :type config_path: str

    :param defaults: Optional default configuration dictionary to merge loaded
        configuration into. If provided, it will be modified in place.
    :type defaults: dict | None

    :return: The result configuration dictionary and if we successfully loaded
        a JSON dictionary from the given filepath.
    :rtype: (dict, bool)

    """
    if defaults is None:
        defaults = {}
    loaded = False
    if config_path and os.path.isfile(config_path):
        with open(config_path) as cf:
            configuration.merge_configs(defaults, json.load(cf))
            loaded = True
    return defaults, loaded


def output_config(output_path, config_dict, log=None, overwrite=False,
                  error_rc=1):
    """
    If a valid output configuration path is provided, we output the given
    configuration dictionary as JSON or error if the file already exists (when
    overwrite is False) or cannot be written. We exit the program as long as
    ``output_path`` was given a value, with a return code of 0 if the file was
    written successfully, or the supplied return code (default of 1) if the
    write failed.

    Specified error return code cannot be 0, which is reserved for successful
    operation.

    :raises ValueError: If the given error return code is 0.

    :param output_path: Path to write the configuration file to.
    :type output_path: str

    :param config_dict: Configuration dictionary containing JSON-compliant
        values.
    :type config_dict: dict

    :param overwrite: If we should clobber any existing file at the specified
        path. We exit with the error code if this is false and a file exists at
        ``output_path``.
    :type overwrite: bool

    :param error_rc: Custom integer error return code to use instead of 1.
    ;type error_rc: int

    :param log: Optionally logging instance. Otherwise we use a local one.
    :type log: logging.Logger

    """
    error_rc = int(error_rc)
    if error_rc == 0:
        raise ValueError("Error return code cannot be 0.")
    if log is None:
        log = logging.getLogger(__name__)
    if output_path:
        if os.path.exists(output_path) and not overwrite:
            log.error("Output configuration file path already exists! (%s)",
                      output_path)
            exit(error_rc)
        else:
            log.info("Outputting JSON configuration to: %s", output_path)
            with open(output_path, 'w') as f:
                json.dump(config_dict, f, indent=4, check_circular=True,
                          separators=(',', ': '), sort_keys=True)
            exit(0)


def report_progress(log, state, interval):
    """
    Loop progress reporting function that logs (when in debug) loops per
    second, loops in the last reporting period and total loops executed.

    The ``state`` given to this function must be a list of 7 integers, initially
    all set to 0. This function will update the fields of the state as its is
    called to control when reporting should happen and what to report.

    A report can be effectively force for a call by setting ``state[3] = 0``
    or ``interval`` to ``0``.

    :param log: Logger logging function to use to send reporting message to.
    :type log: (str, *args) -> None

    :param state: Reporting state. This should be initialized to a list of 6
        zeros (floats), and then should not be modified externally from this
        function.
    :type state: list[float]

    :param interval: Frequency in seconds that reporting messages should be
        made. This should be greater than 0.
    :type interval: float

    """
    # State format:
    #   [lc, c, dc, lt, t, dt, st]
    #   [ 0, 1,  2,  3, 4,  5,  6]

    # Starting time
    if not state[6]:
        state[3] = state[6] = time.time()

    state[1] += 1
    state[4] = time.time()
    state[5] = state[4] - state[3]
    if state[5] >= interval:
        state[2] = state[1] - state[0]
        # TODO: Could possibly to something with ncurses
        #       - to maintain a single line.
        log("Loops per second %f (avg %f) (%d this interval / %d total)",
            state[2] / state[5],
            state[1] / (state[4] - state[6]),
            state[2], state[1])
        state[3] = state[4]
        state[0] = state[1]


def basic_cli_parser(description=None):
    """
    Generate an ``argparse.ArgumentParser`` with the given description and the
    basic options for verbosity and configuration/generation paths.

    The returned parser instance has an option for extra verbosity
    (-v/--verbose) and a group for configuration specification (-c/--config and
    configuration generation (-g/--generate-config).

    :param description: Optional description string for the parser.
    :type description: str

    :return: Argument parser instance with basic options.
    :rtype: argparse.ArgumentParser

    """
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('-v', '--verbose',
                        default=False, action='store_true',
                        help='Output additional debug logging.')

    g_config = parser.add_argument_group('Configuration')
    g_config.add_argument('-c', '--config',
                          metavar="PATH",
                          help='Path to the JSON configuration file.')
    g_config.add_argument('-g', '--generate-config',
                          metavar="PATH",
                          help='Optionally generate a default configuration '
                               'file at the specified path. If a '
                               'configuration file was provided, we update '
                               'the default configuration with the contents '
                               'of the given configuration.')

    return parser


def utility_main_helper(default_config, parser_description=None,
                        parser_extension=lambda p: p):
    """
    Helper function for utilities standardizing logging initialization, CLI
    parsing and configuration loading/generation.

    Specific utilities should use this as their main function. This
    encapsulates the following standard actions:

        - generating ``argparse`` parser (see ``basic_cli_parser``) and parsing
          CLI arguments.
        - handling configuration merger onto the default
        - handling configuration generation based on given default and possibly
          specified input config.

    This takes a hook function ``parser_extension``, which is a function that
    takes the ``ArgumentParser`` instance to allow for adding additional
    arguments and groups.

    :param default_config: Default configuration (JSON) dictionary for the
        utility.
    :type default_config: dict

    :param parser_description: Optional description to give to the generated
        argument parser.
    :type parser_description: str

    :param parser_extension: Function to extend argparse parser.
    :type parser_extension: (argparse.ArgumentParser) -> argparse.ArgumentParser

    :return: Parsed arguments structure and loaded configuration dictionary.
    :rtype: (argparse.Namespace, dict)

    """
    parser = parser_extension(
        basic_cli_parser(description=parser_description)
    )
    args = parser.parse_args()

    config_filepath = args.config
    config_generate = args.generate_config
    verbose = args.verbose

    llevel = logging.INFO
    if verbose:
        llevel = logging.DEBUG
    initialize_logging(logging.getLogger(), llevel)

    config, config_loaded = load_config(config_filepath, default_config)
    output_config(config_generate, config, overwrite=True)

    if not config_loaded:
        raise RuntimeError("No configuration loaded (not trusting default).")

    return args, config
