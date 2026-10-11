"""从唯一剧本导出配音准备资料；不合成、不下载、不改写声音参考。"""
import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import wave
import zipfile
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', default='EP001')
    args = parser.parse_args()
    if not re.fullmatch(r'EP\d{3}', args.episode):
        parser.error('episode 应为 EP001 格式')
    root = Path(__file__).resolve().parents[1]
    ep = root / '剧集' / args.episode
    source = ep / '剧本.md'
    source_bytes = source.read_bytes()
    script = source_bytes.decode('utf-8')
    rows, scene, local = [], None, 0
    for line in script.splitlines():
        header = re.match(r'## (EP\d+-SC\d+) ', line)
        if header:
            scene, local = header[1], 0
        match = re.match(r'(?:\[(VO|OS)\] )?(饭团|紫菜|旁白|广播员)（(.*?)）：(.+)$', line)
        if match:
            if scene is None:
                raise ValueError('台词缺少场次')
            local += 1
            kind, role, performance, text = match.groups()
            rows.append(dict(id=f'{scene}-L{local:02d}', scene=scene,
                             role=role, kind=kind or '对白', text=text,
                             performance=performance,
                             reference='参考原声/饭团_用户视频原声.wav' if role == '饭团' else '待选型',
                             status='待合成；非已生成音频'))
    if not rows:
        raise ValueError('未找到可导出的台词')
    wav = root / '输入/声音参考/饭团_用户视频原声.wav'
    video = root / '输入/声音参考/饭团_用户指定声音原视频.mp4'
    with wave.open(str(wav), 'rb') as f:
        audio = dict(seconds=round(f.getnframes()/f.getframerate(), 3),
                     sample_rate=f.getframerate(), channels=f.getnchannels(),
                     sample_width_bytes=f.getsampwidth(), listening_status='unverified')
    if not video.is_file():
        raise FileNotFoundError(video)
    parent = ep / '制作成果/音频准备'
    parent.mkdir(parents=True, exist_ok=True)
    revision = 1
    while (parent / f'{args.episode}_台词与原声参考_v{revision:03d}').exists():
        revision += 1
    out = parent / f'{args.episode}_台词与原声参考_v{revision:03d}'
    out.mkdir()
    (out / '参考原声').mkdir()
    (out / '按角色台词').mkdir()
    for p in [wav, video]:
        dst = out / '参考原声' / p.name
        shutil.copyfile(p, dst)
        assert hashlib.sha256(p.read_bytes()).digest() == hashlib.sha256(dst.read_bytes()).digest()
    def write(name, text):
        (out / name).write_text(text, encoding='utf-8', newline='\n')
    readme = f'''{args.episode} 台词与原声准备资料

本包只有原声参考和台词文本，没有合成的新对白或背景音乐。
台词来自剧本.md；表演说明不朗读，画面文字不朗读。共{len(rows)}个发声事件。
饭团使用用户指定参考音色；紫菜为稳重女声，具体声音待试听。
童趣是漫画视觉与轻松日常基调，不擅自将饭团改成夸张奶音。

参考原声：{audio['seconds']}秒，{audio['sample_rate']}Hz，{audio['channels']}声道，原样复制。
文件可读与技术参数已核对，尚未完成听辨，不能声称音色、底噪或参考原文已验证。
原声只作音色来源，不能直接当作本集新台词成品，也不循环拉长。

使用顺序：
1. 先看首轮试听选句.txt，后续用小样确认两位主角的声音。
2. 按角色台词/ 内每句的“朗读文本”合成，保留单句干声；说明文字不要送入朗读正文。
3. 逐句回听原文、角色、停顿与音色，再组合成对应15秒视频批次的参考音频。
4. 15秒是即梦每次生成的时长，不要求每句音频15秒；45秒总长仍为建议。
5. 背景音乐独立制作，试音保持干净；片内字幕关闭。

脚本方法见制作方法.md。本包为私用制作资料，包含用户原始声音；不是公开发布素材。
'''
    write('先读我.txt', readme)
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter='\t', lineterminator='\n')
    writer.writerow(['台词ID', '场次', '角色', '声源', '朗读原文', '表演说明（不朗读）', '音色参考', '状态'])
    for row in rows:
        writer.writerow([row[k] for k in ['id','scene','role','kind','text','performance','reference','status']])
    write('全剧配音表.tsv', output.getvalue())
    for role in dict.fromkeys(row['role'] for row in rows):
        parts = [f'{role}｜逐句原文\n说明与编号不朗读；每句单独生成，不把全文件一次送入纯文本朗读。\n']
        for row in rows:
            if row['role'] == role:
                parts.append(f"\n{row['id']}\n朗读文本：{row['text']}\n表演说明：{row['performance']}\n")
        write(f'按角色台词/{role}.txt', ''.join(parts))
    trial = [row for row in rows if row['scene'].endswith(('SC001', 'SC003'))]
    write('首轮试听选句.txt', '工作建议：先试商量出发两句，再用出租车三句检查较长对话。\n全部使用剧本原句；本文件不是已生成音频。先干声，不加配乐或环境声。\n\n' + '\n\n'.join(
        f"{row['id']} {row['role']}\n朗读文本：{row['text']}\n表演说明：{row['performance']}" for row in trial))
    method = root / '项目开发/音视频制作方法.md'
    if method.exists():
        shutil.copyfile(method, out / '制作方法.md')
    manifest = dict(episode=args.episode, status='preparation_only', generated_audio=False,
                    source='剧集/'+args.episode+'/剧本.md',
                    source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                    dialogue_count=len(rows), per_role=dict(Counter(x['role'] for x in rows)),
                    reference_audio=audio, files=[])
    for p in sorted(out.rglob('*')):
        if p.is_file():
            manifest['files'].append(dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size,
                                         sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    write('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    assert source.read_bytes() == source_bytes, '导出期间剧本已变动，请重新导出'
    archive = out.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    print(json.dumps(dict(folder=str(out), archive=str(archive), dialogue_count=len(rows),
                         per_role=manifest['per_role'], reference_audio=audio), ensure_ascii=False))


if __name__ == '__main__':
    main()
