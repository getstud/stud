import tempfile, unittest, uuid
from pathlib import Path
from comments import CommentStore

class CommentsTests(unittest.TestCase):
    def test_persist_dedupe_and_resolve(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'comments.json';s=CommentStore(path)
            model={'revision':'abc','parts':[{'id':'a','assembly':'floor','stock':'wood','size':[1,2,3],'origin':[0,0,0],'rotation':[0,0,0]}]}
            payload={'id':str(uuid.uuid4()),'part_id':'a','text':' Change this <board>\nplease '}
            s.update(payload,model);s.update(payload,model)
            rows=CommentStore(path).read();self.assertEqual(len(rows),1);self.assertEqual(rows[0]['text'],'Change this <board>\nplease');self.assertEqual(rows[0]['revision'],'abc')
            s.update({'action':'resolve','id':payload['id'],'resolved':True},None)
            self.assertTrue(s.read()[0]['resolved'])
            with self.assertRaises(ValueError):s.update({'id':str(uuid.uuid4()),'part_id':'missing','text':'test'},model)
            self.assertEqual(len(s.read()),1)
    def test_invalid_input_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as d:
            s=CommentStore(Path(d)/'comments.json')
            with self.assertRaises(ValueError):s.update({'text':' '},None)
            self.assertEqual(s.read(),[])
