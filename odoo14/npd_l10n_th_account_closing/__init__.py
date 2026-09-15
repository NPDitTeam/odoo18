from . import models


def post_init_hook(env):
    env["res.company"].search([])._npd_setup_thai_closing()
