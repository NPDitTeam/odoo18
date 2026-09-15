from . import models
from . import wizard


def post_init_hook(env):
    """สร้างหมวดสินทรัพย์ตาม o14 ให้ทุกบริษัท (รันซ้ำได้จาก shell: _npd_seed_asset_profiles)"""
    env['account.asset.profile']._npd_seed_asset_profiles()
