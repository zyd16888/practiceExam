import pandas as pd
import json
import re
import sqlite3
import glob
import os

def parse_options(option_str, question_type):
    """
    将 'A-内容|B-内容' 或 'A.内容|B.内容' 格式转换为 JSON 字符串
    """
    # 1. 处理空值：如果是判断题且为空，自动补全标准选项
    if pd.isna(option_str) or str(option_str).strip() == "":
        if question_type == "判断题":
            return json.dumps({"A": "正确", "B": "错误"}, ensure_ascii=False)
        return json.dumps({}, ensure_ascii=False)

    option_str = str(option_str).strip()
    options = {}
    
    # 2. 尝试按竖线 '|' 分割
    # 注意：Excel里有时候可能会有换行符，先简单处理一下
    option_str = option_str.replace('\n', '|')
    items = re.split(r'\|', option_str)
    
    for item in items:
        item = item.strip()
        if not item: continue
        
        # 3. 正则匹配：支持 A-xxx, A.xxx, A、xxx
        # 匹配首字母 (A-Z) 后跟 (., -, 、) 
        match = re.match(r'^([A-Z])\s*[-.、]\s*(.*)', item)
        if match:
            key = match.group(1)
            val = match.group(2)
            options[key] = val
        else:
            # 容错处理：假设首字母是选项key (如 "A内容")
            if len(item) > 1 and item[0].isalpha() and item[0].isupper():
                 options[item[0]] = item[1:].strip(" .、-")
    
    return json.dumps(options, ensure_ascii=False)

def process_excel_files():
    # 1. 查找目录下所有的 .xlsx 和 .xls 文件
    # 排除掉临时文件（以 ~$ 开头）
    files = [f for f in (glob.glob("*.xlsx") + glob.glob("*.xls")) if not os.path.basename(f).startswith('~$')]
    
    all_data = []
    
    print(f"找到 {len(files)} 个Excel文件...")

    for f in files:
        try:
            print(f"正在读取: {f}")
            # 读取 Excel，默认读取第一个 Sheet
            # dtype=str 强制所有内容按字符串读取，防止数字被自动转成浮点数（如题目编号）
            df = pd.read_excel(f, dtype=str)
            
            # 简单清洗列名空格
            df.columns = [str(c).strip() for c in df.columns]
            
            # 如果表格里没有'一级纲要'列，或者为空，可以用文件名作为默认分类
            if '一级纲要' not in df.columns:
                df['一级纲要'] = os.path.splitext(f)[0] # 使用文件名作为分类
            
            all_data.append(df)
        except Exception as e:
            print(f"读取失败 {f}: {e}")

    if not all_data:
        print("未找到Excel文件，请检查路径。")
        return

    # 2. 合并所有数据
    full_df = pd.concat(all_data, ignore_index=True)
    
    # 3. 重命名列以匹配数据库字段
    # 根据你提供的表头：['序号', '一级纲要', '二级纲要', '题目分类', '题型', '题干', '选项', '答案', '题目依据', ...]
    rename_map = {
        '一级纲要': 'category',
        '题型': 'type',
        '题干': 'question',
        '答案': 'answer',
        '题目依据': 'explanation',
        '试题分数': 'score',
        '试题编码': 'codeId',
        '备注': 'remarks',
        '说明': 'Description',
        '判断题解析': 'analysis'
    }
    full_df = full_df.rename(columns=rename_map)
    
    # 4. 数据清洗
    print("正在清洗数据...")
    # 去掉空题干
    full_df = full_df.dropna(subset=['question']) 
    # 清洗答案：转大写，去空格
    full_df['answer'] = full_df['answer'].fillna('').astype(str).str.upper().str.strip()
    
    # 5. 应用选项解析
    # 这一步比较耗时，如果数据量很大(几万条)请耐心等待
    full_df['options'] = full_df.apply(lambda row: parse_options(row.get('选项'), row.get('type')), axis=1)
    
    # 6. 筛选最终需要的列
    final_cols = ['category', 'type', 'question', 'options', 'answer', 'explanation', 'analysis', 'score', 'codeId', 'remarks', 'Description']
    # 确保列都存在
    existing_cols = [c for c in final_cols if c in full_df.columns]
    result_df = full_df[existing_cols]

    # 为每道题增加一个简单的自增 id，便于后续前后端定位题目
    # 注意：这里的 id 仅保证在当前题库中的唯一性，不作为 SQLite 主键使用
    result_df.insert(0, 'id', range(1, len(result_df) + 1))
    
    # 7. 保存结果
    # 保存 CSV 用于检查
    result_df.to_csv("cleaned_questions.csv", index=False, encoding='utf-8-sig')
    
    # 保存 SQLite 数据库
    db_path = "questions.db"
    conn = sqlite3.connect(db_path)
    result_df.to_sql("questions", conn, if_exists="replace", index=False)
    conn.close()
    
    print(f"处理完成！\n共导入 {len(result_df)} 道题目。\n数据库已生成: {db_path}")

if __name__ == "__main__":
    process_excel_files()
