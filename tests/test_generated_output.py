import contextlib
import io
import json
import unittest
from pathlib import Path
import hashlib
from unittest.mock import patch
import main
import starintel_canonical as runtime

class OutputTests(unittest.TestCase):
    def test_actual_ollama_generation_emits_only_generated_documents(self):
        from generators import GENERATORS
        samples={"person":{"fname":"Ada","lname":"Lovelace","dob":"1815-12-10","custom":"retain"},
                 "socialmediapost":{"content":"post","user":"unresolved-user","media":["unresolved-media"],"replyCount":3},
                 "message":{"content":"hello","platform":"test","isReply":False,"user":"unresolved-user"}}
        for kind,raw in samples.items():
            with self.subTest(kind=kind):
                output=io.StringIO()
                with patch('httpx.Client.post') as post, contextlib.redirect_stdout(output):
                    post.return_value.json.return_value={"response":json.dumps(raw)}
                    main.generate_documents(kind,1,'test','model','https://ollama.example')
                doc=json.loads(output.getvalue())
                runtime.validate_document(doc)
                self.assertEqual(doc['extensions']['starintel.synthdata']['input']['ollamaResponse'], json.dumps(raw))
                self.assertEqual(json.loads(doc['extensions']['starintel.synthdata']['input']['ollamaResponse']),raw)
                self.assertEqual(doc['schemaVersion'],'0.10.1')
                self.assertNotIn('_id',doc)
                self.assertNotIn('data',doc)
                self.assertEqual(doc['extensions']['starintel.synthdata']['input']['dtype'],kind)
                if kind=='message':
                    self.assertEqual(doc['message'],'hello')
                    self.assertFalse(doc['isReply'])
                if kind!='person':self.assertEqual(doc['extensions']['starintel.synthdata']['input']['user'],'unresolved-user')
                post.assert_called_once()

    def test_projection_preserves_unknown_and_incompatible_input(self):
        raw={'fname':'Ada','dob':'invalid-date','custom':{'flag':False,'nil':None}}
        doc=main.canonical_document('person',raw,'test')
        runtime.validate_document(doc)
        self.assertNotIn('dob',doc)
        self.assertEqual(doc['extensions']['starintel.synthdata']['input'],raw)

    def test_installed_runtime_matches_the_complete_source_release(self):
        lock=json.loads((Path(__file__).parents[1]/'schema/starintel-schema.lock.json').read_text())
        release=Path(runtime.__file__).parent/'_release'
        for path,entry in lock['vendored_files'].items():
            relative=entry['source'].split('/0.10.1/',1)[1]
            self.assertEqual(hashlib.sha256((release/relative).read_bytes()).hexdigest(),entry['sha256'],relative)

    def test_invalid_required_fields_fail_without_emitting_wire_documents(self):
        output=io.StringIO()
        errors=io.StringIO()
        with patch('httpx.Client.post') as post,contextlib.redirect_stdout(output),contextlib.redirect_stderr(errors):
            post.return_value.json.return_value={'response':json.dumps({'content':False})}
            self.assertEqual(main.generate_documents('message',1,'test','model','https://ollama.example'),1)
        self.assertEqual(output.getvalue(),'')
        self.assertIn('Error generating document:',errors.getvalue())
