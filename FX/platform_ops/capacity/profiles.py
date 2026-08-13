PROFILES=("BASELINE","1X","2X","5X","PEAK_DEFINED")
def ordered(profile):return PROFILES.index(profile)
def may_advance(current,next_profile,healthy):return healthy is True and ordered(next_profile)==ordered(current)+1
