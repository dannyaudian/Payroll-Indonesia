# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors


def on_app_init():
    """Jalankan saat app diinisialisasi"""
    from payroll_indonesia import patch_get_versions

    patch_get_versions()
