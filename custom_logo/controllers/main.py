# -*- coding: utf-8 -*-
import re
from odoo.addons.web.controllers.database import Database


CUSTOM_LOGO_URL = '/custom_logo/static/src/img/custom_logo.png'


class DatabaseCustomLogo(Database):

    def _render_template(self, **d):
        html = super()._render_template(**d)
        new_img = '<img src="{}" class="img-fluid d-block mx-auto" style="max-height:120px; width:auto;"/>'.format(CUSTOM_LOGO_URL)
        html = re.sub(r'<img[^>]*logo2\.png[^>]*/?>',  new_img, html)
        return html
