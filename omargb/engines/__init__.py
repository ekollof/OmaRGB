"""Theme engines. Each one paints the devices the catalog assigned to it."""

from omargb.engines.asus_rog import AsusRog
from omargb.engines.framework16 import Framework16
from omargb.engines.homeassistant import HomeAssistant
from omargb.engines.openlinkhub import OpenLinkHub
from omargb.engines.openrgb import OpenRgb
from omargb.engines.vanguard_k08 import VanguardK08

ENGINES = {
    engine.name: engine
    for engine in (
        VanguardK08(),
        OpenRgb(),
        OpenLinkHub(),
        AsusRog(),
        Framework16(),
        HomeAssistant(),
    )
}
