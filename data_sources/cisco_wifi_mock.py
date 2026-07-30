import random


def get_wifi_count(spike=False):
    if spike:
        return random.randint(60, 80)
    return random.randint(20, 45)
