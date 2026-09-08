import unittest
from stud import gable_end_frame
from test_roof_assemblies import roof_project, failures


def add_gables(p,r):
    caps=[]
    for end,x in enumerate((0,r.interfaces['length']-3.5)):
        pid=f'cap.{end}'
        p.box(pid,'Caps','plate',**r.frame.box((x,3.5,-1.5),(3.5,r.interfaces['span']-7,1.5)))
        caps.append([pid])
    return gable_end_frame(p,'g',roof=r,stud_stock='plate',plate_ids=caps)


class GableTests(unittest.TestCase):
    def test_notched_studs_fit_transformed_roof_and_caps(self):
        for angle,inward in ((0,1),(90,1),(180,-1),(37,-1)):
            with self.subTest(angle=angle,inward=inward):
                p,r=roof_project(angle,inward)
                g=add_gables(p,r)
                self.assertEqual(len(g.part_ids),18)
                self.assertFalse(failures(p),failures(p))
                self.assertTrue(all('bands' in part['profile'] for part in p.parts if part['id'] in g.part_ids))

    def test_missing_stud_and_removed_notch_are_detected(self):
        for change in ('missing','notch','short'):
            p,r=roof_project();g=add_gables(p,r)
            part=next(part for part in p.parts if part['id']==g.part_ids[0])
            if change=='missing':p.parts.remove(part)
            elif change=='notch':part.pop('profile')
            else:part['origin'][2]-=.5
            self.assertTrue(failures(p),change)

    def test_wide_ridge_does_not_overlap_near_peak_stud(self):
        p,r=roof_project()
        # Use a wider structural ridge in an independent roof with a shifted peak.
        from stud import gable_roof
        p.parts.clear();p.validation.clear()
        p.stock('wide','Wide ridge','#aaa',section=(3.5,9.25),lengths=(240,))
        for i,y in enumerate((0,152.5)):
            p.box(f'plate.{i}','Plates','plate',**r.frame.box((0,y,-1.5),(192,3.5,1.5)))
        r=gable_roof(p,'wide_roof',length=192,span=156,pitch=6,plate_depth=3.5,rafter_stock='rafter',ridge_stock='wide',system='structural_ridge',plate_ids=(['plate.0'],['plate.1']),frame=r.frame,maximum_notch=2,minimum_remaining=5,notch_basis='Test')
        add_gables(p,r)
        self.assertFalse(failures(p),failures(p))
