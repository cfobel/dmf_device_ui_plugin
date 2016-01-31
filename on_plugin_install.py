from datetime import datetime
import logging

from path_helpers import path
from pip_helpers import install


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logging.info(str(datetime.now()))
    requirements_file = path(__file__).parent.joinpath('requirements.txt')
    if requirements_file.exists():
        # Install required packages using `pip`, with Wheeler Lab wheels server
        # for binary wheels not available on `PyPi`.
        logging.info(install(['--find-links http://192.99.4.95',
                              '--trusted-host 192.99.4.95', '-r',
                              requirements_file]))
