import random


def get_poe_consumption(spike=False):
    """Returns current PoE switch power draw in watts."""
    if spike:
        return random.uniform(8500, 9500)
    return random.uniform(5800, 6400)
