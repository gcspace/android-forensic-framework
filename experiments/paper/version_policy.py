#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本适配策略表（论文口径）。

本表按"落盘位置 + 媒体权限模型"分四档：legacy_global / legacy_optout / scoped_enforced / granular_media / granular_photo，
作为探针、跑数与正文表述的统一口径。

边界说明：adb shell 拥有较宽的文件系统权限，无法完全复现应用沙箱。
本表描述的是系统层可观测的规则，应用内 MediaStore/SAF 行为需由原型应用验证，
脚本只负责把系统层证据采集齐。
"""

POLICY = {
    28: dict(branch="legacy_global", legacy_writable=True, mediastore="可选",
             saf=False, granular_media=False, photo_picker=False,
             label="分区存储前，全局文件路径"),
    29: dict(branch="legacy_optout", legacy_writable=True, mediastore="可用",
             saf=True, granular_media=False, photo_picker=False,
             label="分区存储可退出（requestLegacyExternalStorage）"),
    30: dict(branch="scoped_enforced", legacy_writable=False, mediastore="强制",
             saf=True, granular_media=False, photo_picker=False,
             label="分区存储强制执行"),
    31: dict(branch="scoped_enforced", legacy_writable=False, mediastore="强制",
             saf=True, granular_media=False, photo_picker=False,
             label="分区存储强制执行"),
    32: dict(branch="scoped_enforced", legacy_writable=False, mediastore="强制",
             saf=True, granular_media=False, photo_picker=False,
             label="分区存储强制执行"),
    33: dict(branch="granular_media", legacy_writable=False, mediastore="强制",
             saf=True, granular_media=True, photo_picker=False,
             label="细粒度媒体权限 READ_MEDIA_*"),
    34: dict(branch="granular_photo", legacy_writable=False, mediastore="强制",
             saf=True, granular_media=True, photo_picker=True,
             label="细粒度媒体权限 + 部分照片访问"),
    35: dict(branch="granular_photo", legacy_writable=False, mediastore="强制",
             saf=True, granular_media=True, photo_picker=True,
             label="细粒度媒体权限 + 部分照片访问"),
}

DEFAULT_API = 33


def policy_for(api_level):
    """返回某一 API 级别的策略字典；未知级别抛 ValueError，避免静默归入某档。"""
    api = int(api_level)
    if api not in POLICY:
        raise ValueError("未定义 API %d 的版本策略，请先在 version_policy.POLICY 中补充" % api)
    return dict(POLICY[api], api=api)


def branch_for(api_level):
    return policy_for(api_level)["branch"]


def legacy_writable(api_level):
    return policy_for(api_level)["legacy_writable"]


if __name__ == "__main__":
    print("API\t分支\t\t\t/sdcard可写\tMediaStore\tSAF\t细粒度媒体\t部分照片")
    for api in sorted(POLICY):
        p = POLICY[api]
        print("%d\t%-16s\t%s\t\t%s\t\t%s\t%s\t\t%s" % (
            api, p["branch"], "是" if p["legacy_writable"] else "否",
            p["mediastore"], "有" if p["saf"] else "无",
            "有" if p["granular_media"] else "无",
            "有" if p["photo_picker"] else "无"))
