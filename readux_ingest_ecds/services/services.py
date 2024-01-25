""" Utility functions for fetching remote data. """
import json
import logging
import requests

logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.ERROR)

def fetch_url(url, timeout=30, data_format='json', verbosity=1):
    """ Given a url, this function returns the data."""
    data = None
    try:
        resp = requests.get(url, timeout=timeout, verify=True)
    except requests.exceptions.Timeout as err:
        if verbosity > 2:
            logger.warning('Connection timeoutout for {}'.format(url))
        return data
    except Exception as err:
        if verbosity > 2:
            logger.warning('Connection failed for {}. ({})'.format(url, str(err)))
        return data

    if resp.status_code != 200:
        if verbosity > 2:
            logger.warning('Connection failed status {}. ({})'.format(url, resp.status_code))
        return data

    if data_format == 'json':
        try:
            data = resp.json()
        except json.decoder.JSONDecodeError as err:
            if verbosity > 2:
                logger.warning('Server send success status with bad content {}'.format(url))
        return data

    if data_format == 'text':
        data = resp.text
    else:
        data = resp.content
    return data
