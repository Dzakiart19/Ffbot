import logging
from google.protobuf.message import DecodeError

from garena.proto import like_pb2, uid_generator_pb2, like_count_pb2
from garena.crypto import encrypt_aes

logger = logging.getLogger(__name__)

def build_like_payload(uid: str, region: str) -> str:
    msg = like_pb2.like()
    msg.uid = int(uid)
    msg.region = region
    return encrypt_aes(msg.SerializeToString())

def build_uid_payload(uid: str) -> str:
    msg = uid_generator_pb2.uid_generator()
    msg.saturn_ = int(uid)
    msg.garena = 1
    return encrypt_aes(msg.SerializeToString())

def decode_player_info(data: bytes):
    try:
        info = like_count_pb2.Info()
        info.ParseFromString(data)
        return info
    except DecodeError as e:
        logger.error(f"Protobuf decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected decode error: {e}")
        return None
