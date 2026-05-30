def mock_ai_answer(question, sources):
    if not sources:
        return "関連する情報が見つかりませんでした。"

    return "SQLiteから取得した検索結果をもとに、仮のAI回答を生成しました。"