"""Preview coalescing preserves immutable boundaries and flushes the last one."""
import threading
import unittest

from stud.publication import PreviewPublisher


class PreviewPublicationTests(unittest.TestCase):
    def test_unpublished_add_and_replace_remains_an_add_with_latest_geometry(self):
        writes=[]
        stream=PreviewPublisher(lambda snapshot,changes:writes.append(changes),interval=lambda snapshot:60)
        stream.submit(dict(objects=[]),[])
        stream.submit(dict(objects=[]),[dict(object=dict(id='part',version=1),operation='add')])
        stream.submit(dict(objects=[]),[dict(object=dict(id='part',version=2),operation='replace')])
        stream.close()
        self.assertEqual(writes[-1],[dict(object=dict(id='part',version=2),operation='add')])
        same_batch=[]
        stream=PreviewPublisher(lambda snapshot,changes:same_batch.extend(changes))
        stream.submit(dict(objects=[]),[dict(object=dict(id='part',version=1),operation='add'),dict(object=dict(id='part',version=2),operation='replace')])
        stream.close()
        self.assertEqual(same_batch,writes[-1])

    def test_first_and_last_frames_are_durable_and_changes_are_not_lost(self):
        writes=[]
        stream=PreviewPublisher(lambda snapshot,changes:writes.append((snapshot,changes)),interval=lambda snapshot:60)
        objects=[]
        for index in range(100):
            obj=dict(id=str(index),value=index)
            objects.append(obj)
            stream.submit(dict(objects=objects),[dict(object=obj,operation='add')])
        objects[-1]['value']='later external mutation'
        stream.close()
        self.assertEqual(len(writes),2)
        self.assertEqual(len(writes[0][0]['objects']),1)
        self.assertEqual(len(writes[1][0]['objects']),100)
        self.assertEqual(writes[1][0]['objects'][-1]['value'],99)
        self.assertEqual({entry['object']['id'] for entry in writes[1][1]},{str(i) for i in range(1,100)})

    def test_last_frame_publishes_when_author_stops_producing(self):
        published=threading.Event();writes=[]
        def write(snapshot,changes):
            writes.append(snapshot)
            if len(writes)==2:published.set()
        stream=PreviewPublisher(write,interval=lambda snapshot:.01)
        self.addCleanup(stream.close)
        stream.submit(dict(objects=[]),[])
        stream.submit(dict(objects=[dict(id='finished')]),[])
        self.assertTrue(published.wait(2),'A pause in authoring must not strand the last preview.')

    def test_writer_failures_propagate_at_the_final_flush(self):
        def write(snapshot,changes):
            if snapshot['objects']:raise OSError('Injected disk write failure')
        stream=PreviewPublisher(write,interval=lambda snapshot:60)
        stream.submit(dict(objects=[]),[])
        stream.submit(dict(objects=[dict(id='one')]),[])
        with self.assertRaisesRegex(OSError,'Injected disk write failure'):stream.close()
