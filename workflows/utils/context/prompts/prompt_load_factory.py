from . import prompt_load_local_disk
from . import prompt_load_s3
import logging

logger = logging.getLogger(__name__)

load_map = {

    "local_disk" : prompt_load_local_disk,
    "s3": prompt_load_s3
}

def get_prompt(location: dict[str, str]):

    type_resource = location.get("resource").strip().lower()
    uri = location.get("uri").strip().lower()

    logger.info("location=%r", location)
    logger.info("resource=%r (%s)", type_resource, type(type_resource))
    logger.info("keys=%r", list(load_map.keys()))

    loader = load_map.get(type_resource)

    logger.info("loader=%r", loader)

    return loader.get_prompt(uri)