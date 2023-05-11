import logging

FORMAT = "%(asctime)s-%(levelname)s-%(message)s"


# todo elaborate on levels
def get_logger():
    logging.basicConfig(format=FORMAT)
    logger = logging.getLogger()
    logger.setLevel("INFO")
    return logger
