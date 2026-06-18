# Synapse

> AI 漫剧创作平台，从故事拆解、角色设定、分镜提示词、图像生成、视频生成到成片合成的一体化桌面工作台。

<p>
  <img alt="Windows" src="https://img.shields.io/badge/Windows-desktop-2563eb">
  <img alt="AI Video" src="https://img.shields.io/badge/AI-comic%20drama-7c3aed">
  <img alt="License Key" src="https://img.shields.io/badge/license%20key-required-f97316">
  <img alt="Source Available" src="https://img.shields.io/badge/source-available-111827">
</p>

## Overview

Synapse 是为 AI 漫剧、短剧和故事视频生产设计的桌面软件。它把原本分散在文本模型、图像模型、视频模型和本地剪辑流程里的环节串成一个工作台，适合用来管理长篇故事、多角色一致性和批量镜头生产。

本仓库公开源码用于学习、审阅和技术参考。正式运行软件需要有效卡密。

获取卡密、商业授权或定制开发请联系：

**PhineasGym@outlook.com**

## Features

- Story pipeline: organize novels, outlines, character arcs, and clip-level structure.
- Character system: keep character descriptions, visual anchors, and consistency prompts together.
- Storyboard generation: create reference prompts, tail-frame prompts, motion prompts, and negative prompts.
- Image workflow: call image generation APIs and manage generated keyframes.
- Video workflow: call video generation APIs and track clip outputs.
- Composition workflow: combine generated clips into final videos with local processing.
- Project workspace: keep each drama project isolated with its own assets and outputs.
- Windows distribution: build a standard installer with installation path selection and desktop shortcut support.

## License Key

Synapse uses a license-key activation flow. The source code being visible does not mean the activation system can be removed, bypassed, or redistributed as an unlocked build.

For license keys, commercial use, or private deployment:

**PhineasGym@outlook.com**

## For Developers

This repository is provided for technical review and secondary development reference. Runtime configuration such as model API keys, local projects, generated media, installers, and private license cache files are intentionally excluded from the repository.

Before publishing changes or forks, do not include:

- real API keys
- license keys
- private project data
- generated customer assets
- installer outputs
- local cache files

## Distribution

The official Windows installer bundles the required runtime assets for end users. Users should install Synapse through the packaged installer rather than manually assembling runtime files.

Installer features:

- custom installation path
- desktop shortcut
- Start Menu shortcut
- standard uninstall entry

## Source Availability

This is a source-available project. You may read and study the code, but commercial redistribution, resale, sublicensing, removal of the activation flow, or publishing unlocked derivative builds requires prior written permission from the author.

See [LICENSE](LICENSE) for details.

## Contact

**PhineasGym@outlook.com**
