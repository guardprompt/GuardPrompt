-- Dedupe identiškų paveiksliukų iš chat.files masyvų.
-- Preventyvu: BEFORE INSERT/UPDATE — dublikatas niekada nepatenka į DB.
-- Idempotentu: saugu vykdyti kartotinai (CREATE OR REPLACE + DROP/CREATE).

CREATE OR REPLACE FUNCTION dedupe_chat_files() RETURNS trigger AS $$
DECLARE
    j        jsonb;
    hist     jsonb;
    new_hist jsonb;
    msgs     jsonb;
    new_msgs jsonb;
    k        text;
    msg      jsonb;
    files    jsonb;
    deduped  jsonb;
BEGIN
    j := NEW.chat::jsonb;

    -- 1) history.messages (objektas: msgId -> žinutė)
    hist := j #> '{history,messages}';
    IF hist IS NOT NULL AND jsonb_typeof(hist) = 'object' THEN
        new_hist := hist;
        FOR k, msg IN SELECT * FROM jsonb_each(hist) LOOP
            files := msg -> 'files';
            IF files IS NOT NULL AND jsonb_typeof(files) = 'array' THEN
                SELECT jsonb_agg(elem ORDER BY ord) INTO deduped
                FROM (
                    SELECT elem, min(ord) AS ord
                    FROM jsonb_array_elements(files) WITH ORDINALITY AS t(elem, ord)
                    GROUP BY elem
                ) s;
                new_hist := jsonb_set(new_hist, ARRAY[k, 'files'], COALESCE(deduped, '[]'::jsonb));
            END IF;
        END LOOP;
        j := jsonb_set(j, '{history,messages}', new_hist);
    END IF;

    -- 2) messages (masyvas)
    msgs := j -> 'messages';
    IF msgs IS NOT NULL AND jsonb_typeof(msgs) = 'array' THEN
        SELECT jsonb_agg(
            CASE
                WHEN (m -> 'files') IS NOT NULL AND jsonb_typeof(m -> 'files') = 'array'
                THEN jsonb_set(m, '{files}', COALESCE(
                    (SELECT jsonb_agg(elem ORDER BY ord)
                     FROM (
                        SELECT elem, min(ord) AS ord
                        FROM jsonb_array_elements(m -> 'files') WITH ORDINALITY AS t(elem, ord)
                        GROUP BY elem
                     ) s),
                    '[]'::jsonb))
                ELSE m
            END
            ORDER BY midx
        ) INTO new_msgs
        FROM jsonb_array_elements(msgs) WITH ORDINALITY AS mm(m, midx);
        IF new_msgs IS NOT NULL THEN
            j := jsonb_set(j, '{messages}', new_msgs);
        END IF;
    END IF;

    NEW.chat := j::json;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_dedupe_chat_files ON chat;
CREATE TRIGGER trg_dedupe_chat_files
    BEFORE INSERT OR UPDATE ON chat
    FOR EACH ROW EXECUTE FUNCTION dedupe_chat_files();

-- Vienkartinis esamų chat'ų sutvarkymas (trigger suveiks per UPDATE)
UPDATE chat SET chat = chat;
