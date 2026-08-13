#!/usr/bin/env python3
"""Validate Symphony self-contained visual, workflow, casting, and setting rules."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


IMAGE_FILENAME_RE = re.compile(r"(?i)\b[^\s/\\]+\.(?:png|jpe?g|webp)\b")
REFERENCE_NUMBER_RE = re.compile(r"参考图\s*(\d+)")
OPTIONAL_UPLOAD_RE = re.compile(
    r"(?:推荐|建议|可选|按需).{0,12}(?:上传|参考图)|"
    r"(?:上传|参考图).{0,12}(?:推荐|建议|可选|按需)"
)
WORKFLOW_META_RE = re.compile(
    r"本提示词|唯一依赖|必传|用户|上传|可选参考图|推荐参考图|"
    r"(?:图片|产品图)?文件名|已批准|未批准|审核|事实边界|交付|"
    r"任务目录|文件路径"
)
AMERICAN_CAST_RE = re.compile(
    r"美国白人|白人美国人|美国黑人|黑人美国人|非裔美国人|"
    r"\b(?:white american|black american|african[ -]american)"
    r"(?:s|\s+(?:actor|actors|person|people))?\b",
    re.IGNORECASE,
)
NO_PEOPLE_RE = re.compile(
    r"(?:画面|全片|视频).{0,8}(?:中)?(?:不出现|没有|无)(?:任何)?人物|"
    r"\bno\s+(?:visible\s+)?(?:people|persons|humans)\b",
    re.IGNORECASE,
)
NO_ASIAN_FACE_RE = re.compile(
    r"(?:不出现|不得出现|没有|无|避免).{0,10}(?:亚洲|东亚).{0,8}(?:面孔|面貌|脸|人物|演员)?|"
    r"(?:亚洲|东亚).{0,8}(?:面孔|面貌|脸|人物|演员).{0,10}(?:不出现|不得出现|没有|无|避免)|"
    r"\b(?:no|without|exclude|excluding|avoid)\s+(?:any\s+)?(?:asian|east asian)\s+"
    r"(?:face|faces|people|persons|actors)\b",
    re.IGNORECASE,
)
AMERICAN_SETTING_RE = re.compile(
    r"美式|美国(?:家庭|住宅|家居|装修|客厅|卧室|厨房|院落|街头|街道|街景|城市|"
    r"郊区|社区|商圈|停车场|校园|高中|教室|走廊|商店|办公室|环境|场景|建筑)|"
    r"\bamerican(?:-style)?\s+(?:home|house|interior|living room|bedroom|kitchen|street|"
    r"city|suburb|neighborhood|school|high school|classroom|campus|store|office|setting|environment)\b",
    re.IGNORECASE,
)
DIRECT_CHILD_ROLE_RE = re.compile(
    r"儿童|小孩|小朋友|婴儿|幼儿|未成年|男孩|女孩|(?<!青)少年|少女|"
    r"\b(?:child|children|kid|kids|minor|minors|baby|babies|toddler|toddlers|boy|boys|girl|girls)\b",
    re.IGNORECASE,
)
MATURITY_PUSH_RE = re.compile(
    r"18\s*岁(?:或|及)?以上|年满\s*18\s*岁|至少\s*18\s*岁|18\s*岁(?:青年)?成年人|"
    r"\b(?:18\s*(?:years? old)?\s*or older|aged?\s*18\+?|18\+)\b",
    re.IGNORECASE,
)
PERSON_ANCHOR_RE = re.compile(r"人物外观锚点|角色外观锚点")
ENVIRONMENT_ANCHOR_RE = re.compile(r"环境视觉锚点|场景视觉锚点")
PERSON_PHYSICAL_DETAIL_RE = re.compile(
    r"体型|身形|身高|脸型|面部|发型|发色|短发|长发|卷发|直发|"
    r"\b(?:build|body type|height|face|facial|hair|hairstyle)\b",
    re.IGNORECASE,
)
PERSON_CLOTHING_DETAIL_RE = re.compile(
    r"穿|服装|上衣|外套|夹克|连帽衫|针织衫|T恤|衬衫|裙|裤|鞋|"
    r"\b(?:wears?|wearing|clothing|outfit|shirt|jacket|hoodie|sweater|dress|pants|shoes)\b",
    re.IGNORECASE,
)
TIMECODE_RE = re.compile(r"\d+(?:\.\d+)?\s*[–-]\s*\d+(?:\.\d+)?\s*秒")
VISUAL_TIMELINE_RE = re.compile(r"画面\s*[：:]")


def validate(text: str) -> list[str]:
    errors: list[str] = []
    numbers = {int(value) for value in REFERENCE_NUMBER_RE.findall(text)}

    if numbers:
        errors.append(
            "提示词绑定了外部图片编号："
            + ", ".join(f"参考图 {number}" for number in sorted(numbers))
            + "；请改为不依赖图片编号的视觉锚点与时间线"
        )

    filenames = sorted(set(IMAGE_FILENAME_RE.findall(text)))
    if filenames:
        errors.append("提示词包含图片文件名：" + ", ".join(filenames))

    if OPTIONAL_UPLOAD_RE.search(text):
        errors.append("提示词包含可选或推荐上传措辞")

    workflow_meta = sorted(set(WORKFLOW_META_RE.findall(text)))
    if workflow_meta:
        errors.append("提示词包含人类工作流元话术：" + ", ".join(workflow_meta))

    if not TIMECODE_RE.search(text) or not VISUAL_TIMELINE_RE.search(text):
        errors.append("提示词缺少可独立执行的时间码与“画面”时间线")

    if not PERSON_ANCHOR_RE.search(text):
        errors.append("提示词缺少“人物外观锚点”")

    if not ENVIRONMENT_ANCHOR_RE.search(text):
        errors.append("提示词缺少“环境视觉锚点”")

    no_people = bool(NO_PEOPLE_RE.search(text))
    if not no_people and not AMERICAN_CAST_RE.search(text):
        errors.append("提示词缺少美国白人或美国黑人的虚构演员选角")

    if not no_people and not NO_ASIAN_FACE_RE.search(text):
        errors.append("提示词缺少“不出现亚洲面孔”的人物约束")

    if not no_people and not PERSON_PHYSICAL_DETAIL_RE.search(text):
        errors.append("人物外观锚点缺少体型、脸型或发型等稳定外观特征")

    if not no_people and not PERSON_CLOTHING_DETAIL_RE.search(text):
        errors.append("人物外观锚点缺少稳定服装款式或颜色")

    if not AMERICAN_SETTING_RE.search(text):
        errors.append("提示词缺少美式家庭、街头、校园或其他美国环境设定")

    direct_child_roles = sorted(set(DIRECT_CHILD_ROLE_RE.findall(text)))
    if direct_child_roles:
        errors.append(
            "提示词包含过于直接或含混的儿童角色标签："
            + ", ".join(direct_child_roles)
            + "；请根据场景改用“青少年/高中生”"
        )

    maturity_labels = sorted(set(MATURITY_PUSH_RE.findall(text)))
    if maturity_labels:
        errors.append(
            "提示词包含会把年轻人物推向成熟外观的 18+ 声明："
            + ", ".join(maturity_labels)
            + "；请保留“青少年/高中生”的年轻形象"
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Symphony prompt self-contained visual anchors, workflow language, "
            "timeline, American casting/setting, and youth-label rules."
        )
    )
    parser.add_argument("prompt", type=Path)
    args = parser.parse_args()

    text = args.prompt.read_text(encoding="utf-8")
    errors = validate(text)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
