from enum import Enum

class AudioLibrariesEnum(Enum, str):
    audfprint = 1
    SoundFingerprinting = 2

class AudfprintModeEnum(Enum, str):
    accurate = 0
    fast = 1