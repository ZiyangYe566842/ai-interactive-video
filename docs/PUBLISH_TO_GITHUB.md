# 发布到 GitHub

建议仓库名：`ai-interactive-video`。本目录就是仓库根目录；发布源码时，请解压 ZIP 后推送目录内的文件。

## 网页上传

1. 登录 GitHub，点击 **New repository**，仓库名称填写 `ai-interactive-video`。
2. 可见性选择 **Public**。本项目已包含 README 和许可证，无需在网页额外创建。
3. 上传仓库根目录内的所有源码文件。注意包含 `.github`、`.gitignore` 等文件；GameGen 还需要 `.opencode`。命令行推送更容易完整保留这些目录。
4. 首次提交后检查 **Actions** 的 CI；CI 通过后，可按项目版本创建一个 Release。

## GitHub CLI

先安装 Git、GitHub CLI，并完成 `gh auth login`。将 `YOUR_GITHUB_USERNAME` 替换为你自己的账号；组织仓库请使用组织名称。

```bash
cd ai-interactive-video
python3 scripts/check_release.py
git init -b main
git add .
git commit -m "Initial open-source release"
gh repo create YOUR_GITHUB_USERNAME/ai-interactive-video --public --source=. --remote=origin --push
```

如果 Git 提示缺少提交者信息，先设置你希望公开的姓名和 GitHub noreply 邮箱。不要填写 API key 或密码。

仓库创建后，设置 **About** 描述和 topics，可使用下面的建议。

Description: Turn text or video ideas into branching interactive videos with a local demo and configurable AI providers.

Topics: `ai`, `interactive-video`, `storytelling`, `fastapi`, `react`, `video-generation`.

建议首个标签：`v0.2.0`。
