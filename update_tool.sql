UPDATE tool SET content = $$
"""
title: Senų failų valymas
author: GuardPrompt
description: Trina failus senesnius nei nurodytas dienų skaičius. Knowledge bazių failai neliečiami.
version: 1.5
"""

from datetime import datetime, timedelta


class Tools:
    def __init__(self):
        self.citation = False

    async def delete_old_files(self, days: int, __user__: dict = {}) -> str:
        """
        Trina failus senesnius nei nurodyta dienų skaičių. Knowledge bazių failai neliečiami.
        :param days: Failų amžius dienomis (pvz. 30)
        """
        try:
            from open_webui.models.files import Files
            from open_webui.internal.db import get_async_db_context
            from sqlalchemy import text
        except ImportError as e:
            return f"Import klaida: {e}"

        kb_file_ids = set()
        async with get_async_db_context() as db:
            result = await db.execute(text("SELECT file_id FROM knowledge_file"))
            for row in result.fetchall():
                kb_file_ids.add(row[0])

        all_files = await Files.get_files()

        cutoff = datetime.now() - timedelta(days=days)
        deleted, skipped_kb, skipped_new = [], 0, 0

        for f in all_files:
            if f.id in kb_file_ids:
                skipped_kb += 1
                continue
            if datetime.fromtimestamp(f.created_at) < cutoff:
                await Files.delete_file_by_id(f.id)
                deleted.append(f.filename)
            else:
                skipped_new += 1

        return (
            f"Istrinta: {len(deleted)} failu\n"
            f"Praleista (knowledge baze): {skipped_kb}\n"
            f"Praleista (per nauji): {skipped_new}\n"
            + (("\nIstrinti:\n" + "\n".join(f"- {n}" for n in deleted)) if deleted else "")
        )
$$ WHERE id = 'senu_failu_valymas';
