"""Confluence HTML zip 包转换为 Markdown + 图片目录"""
import hashlib
import logging
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

logger = logging.getLogger(__name__)


@dataclass
class _NavNode:
    """导航树节点"""
    title: str
    href: str  # 对应的 HTML 文件名
    children: list["_NavNode"] = field(default_factory=list)


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip().strip(".")


def _parse_nav_tree(ul_tag: Tag) -> list[_NavNode]:
    """递归解析 <ul><li><a> 导航树"""
    nodes: list[_NavNode] = []
    for li in ul_tag.find_all("li", recursive=False):
        a = li.find("a", recursive=False)
        if not a:
            continue
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if not title or not href:
            continue
        node = _NavNode(title=title, href=href)
        child_ul = li.find("ul", recursive=False)
        if child_ul:
            node.children = _parse_nav_tree(child_ul)
        nodes.append(node)
    return nodes


def _find_prefix_dir(tmp_dir: str) -> str:
    """自动检测 zip 内的前缀目录，返回包含 index.html 的根目录"""
    if os.path.isfile(os.path.join(tmp_dir, "index.html")):
        return tmp_dir
    for entry in os.listdir(tmp_dir):
        candidate = os.path.join(tmp_dir, entry)
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "index.html")):
            return candidate
    return tmp_dir


def _html_to_markdown(html_path: str, domain_name: str) -> str:
    """将单个 Confluence 页面 HTML 转换为 Markdown"""
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    # 提取 #main-content 正文，找不到则用 body
    content = soup.find(id="main-content") or soup.find("body") or soup
    if content is None:
        return ""

    # 清理无用标签
    for tag_name in ("script", "style", "nav", "header", "footer"):
        for tag in content.find_all(tag_name):
            tag.decompose()

    # 图片路径改写: attachments/xxx/yyy.png → _attachments/xxx/yyy.png
    for img in content.find_all("img"):
        src = img.get("src", "")
        if src.startswith("attachments/"):
            img["src"] = "_" + src
        elif src.startswith("images/"):
            img["src"] = "_" + src

    html_str = str(content)
    markdown = md(html_str, heading_style="ATX", strip=["a"] if False else None)

    # 清理多余空行
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown


def _write_nav_tree(
    nodes: list[_NavNode],
    parent_dir: str,
    src_root: str,
    domain_name: str,
):
    """递归遍历导航树，生成目录结构和 Markdown 文件"""
    for node in nodes:
        safe_title = _sanitize_filename(node.title)
        if not safe_title:
            safe_title = "untitled"

        html_path = os.path.join(src_root, node.href)
        if not os.path.isfile(html_path):
            logger.warning("页面 HTML 不存在，跳过: %s", node.href)
            continue

        markdown = _html_to_markdown(html_path, domain_name)

        if node.children:
            # 有子节点 → 创建目录
            node_dir = os.path.join(parent_dir, safe_title)
            os.makedirs(node_dir, exist_ok=True)
            md_path = os.path.join(node_dir, f"{safe_title}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)
            _write_nav_tree(node.children, node_dir, src_root, domain_name)
        else:
            # 叶子节点 → 直接写文件
            md_path = os.path.join(parent_dir, f"{safe_title}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)


def convert_confluence_zip(zip_path: str, output_dir: str, domain_name: str) -> bool:
    """
    主入口：将 Confluence 导出的 HTML zip 转换为 Markdown + 图片。

    Args:
        zip_path: zip 文件路径
        output_dir: 输出目录（如 data/wiki/）
        domain_name: 知识域名称（用于日志）

    Returns:
        True 表示执行了转换，False 表示跳过（已是最新）
    """
    hash_file = os.path.join(output_dir, ".confluence_hash")

    # 幂等检查
    current_hash = _md5(zip_path)
    if os.path.isfile(hash_file):
        with open(hash_file, "r") as f:
            existing_hash = f.read().strip()
        if existing_hash == current_hash:
            logger.info("[%s] Confluence zip 已是最新，跳过转换", domain_name)
            return False

    logger.info("[%s] 开始转换 Confluence zip: %s", domain_name, zip_path)

    # 解压到临时目录
    tmp_dir = tempfile.mkdtemp(prefix="confluence_")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)

        src_root = _find_prefix_dir(tmp_dir)
        index_path = os.path.join(src_root, "index.html")
        if not os.path.isfile(index_path):
            logger.error("[%s] zip 中未找到 index.html", domain_name)
            return False

        # 解析导航树
        with open(index_path, "r", encoding="utf-8", errors="replace") as f:
            index_soup = BeautifulSoup(f.read(), "html.parser")

        # 找到 "Available Pages" 下的导航列表
        nav_ul = None
        for header in index_soup.find_all(["h2", "h3", "p", "div"]):
            if "Available Pages" in header.get_text():
                nav_ul = header.find_next("ul")
                break
        if nav_ul is None:
            # 退而求其次：找页面中第一个嵌套 ul
            nav_ul = index_soup.find("ul")
        if nav_ul is None:
            logger.error("[%s] 无法解析导航树", domain_name)
            return False

        nav_tree = _parse_nav_tree(nav_ul)
        if not nav_tree:
            logger.error("[%s] 导航树为空", domain_name)
            return False

        logger.info("[%s] 解析到 %d 个顶级页面", domain_name, len(nav_tree))

        # 清空输出目录（保留 .confluence_hash 以外的内容会被覆盖）
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        # 生成 Markdown 文件
        _write_nav_tree(nav_tree, output_dir, src_root, domain_name)

        # 拷贝附件
        for attach_dir_name in ("attachments", "images"):
            attach_src = os.path.join(src_root, attach_dir_name)
            if os.path.isdir(attach_src):
                attach_dst = os.path.join(output_dir, f"_{attach_dir_name}")
                if os.path.isdir(attach_dst):
                    shutil.rmtree(attach_dst)
                shutil.copytree(attach_src, attach_dst)
                logger.info("[%s] 已拷贝 %s/", domain_name, attach_dir_name)

        # 写入 hash 标记
        with open(hash_file, "w") as f:
            f.write(current_hash)

        logger.info("[%s] Confluence 转换完成，输出: %s", domain_name, output_dir)
        return True

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
