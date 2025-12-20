# POST 请求固定 URL
SIGN_IN_PAGE_URL = "https://zodgame.xyz/plugin.php?id=dsu_paulsign:sign"
CHECKIN_URL = SIGN_IN_PAGE_URL + "&operation=qiandao&infloat=1&inajax=1"

# 固定请求头
HEADERS = {"referer":SIGN_IN_PAGE_URL}

# 签到心情
MOODS = ["kx", "ng", "ym", "wl", "nu", "ch", "fd", "yl", "shuai"]
MOODS_LENGTH = len(MOODS)
