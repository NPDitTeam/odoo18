# -*- coding: utf-8 -*-
"""กันเธรด cron ตายเพราะรายการฐานข้อมูลถูกแก้ระหว่างไล่อ่าน

odoo/service/server.py ไล่อ่านด้วย registries.d.items() ตรง ๆ โดยไม่ถือล็อกของ
LRU ถ้ามีเธรดอื่นโหลดหรือปลดฐานข้อมูลจังหวะเดียวกัน Python จะโยน
RuntimeError: OrderedDict mutated during iteration แล้วเธรด cron ตายถาวร

แก้โดยเปลี่ยน .d เป็น OrderedDict ที่คืนสำเนาเวลาไล่อ่าน ตัวอื่น ๆ ของ LRU
(move_to_end / popitem / del / len) ยังใช้ได้เหมือนเดิมเพราะยังเป็น OrderedDict
"""
import collections
import logging

_logger = logging.getLogger(__name__)


class SnapshotOrderedDict(collections.OrderedDict):
    """OrderedDict ที่คืนสำเนาเวลาไล่อ่าน แทนที่จะคืนมุมมองที่ผูกกับตัวจริง"""

    def items(self):
        return list(collections.OrderedDict.items(self))

    def keys(self):
        return list(collections.OrderedDict.keys(self))

    def values(self):
        return list(collections.OrderedDict.values(self))


def _install_guard():
    try:
        from odoo.modules.registry import Registry
    except Exception:
        _logger.exception('npd_cron_thread_guard: หา Registry ไม่เจอ ข้ามการป้องกัน')
        return

    store = getattr(Registry, 'registries', None)
    current = getattr(store, 'd', None)
    if current is None:
        _logger.warning('npd_cron_thread_guard: โครงสร้าง Registry ไม่ตรงที่คาด ข้ามไป')
        return
    if isinstance(current, SnapshotOrderedDict):
        return

    lock = getattr(store, '_lock', None)
    if lock is not None:
        with lock:
            store.d = SnapshotOrderedDict(current)
    else:
        store.d = SnapshotOrderedDict(current)
    _logger.info('npd_cron_thread_guard: ป้องกันเธรด cron ตายเรียบร้อย (%d ฐาน)',
                 len(store.d))


_install_guard()
