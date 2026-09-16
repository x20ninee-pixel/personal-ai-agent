import logging


def setup_logging():
    """
    Configure structured logging for the whole application.

    Call once, at startup, before anything else logs.
    Never pass API keys, tokens, or raw user message content
    to these loggers.
    """

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | %(levelname)-8s | "
            "%(name)s | %(message)s"
        ),
    )

    # Quiet down noisy third-party loggers so our own
    # events aren't buried.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


def get_logger(name):
    return logging.getLogger(name)
