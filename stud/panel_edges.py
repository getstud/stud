"""Native panel edge evidence, including abstract factory tongue-and-groove joints."""
import cadquery as cq
from .cad import point_at, vector_at
from .contracts import StudError


def _length(shape):
    return sum(edge.Length() for edge in shape.Edges())


def _factory(model, pid, faces):
    entry=model.shapes[pid]
    result=[]
    for joint in (model.objects[pid].get('blank') or {}).get('factory_edges',[]):
        line=cq.Edge.makeLine(*[cq.Vector(*point_at(entry['location'],joint[k])) for k in ('start','end')])
        normal=cq.Vector(*vector_at(entry['location'],joint['outward'])).normalized()
        for face in faces:
            for edge in face.Edges():
                common=edge.intersect(line)
                if _length(common)>1e-7:result.append((common,normal,joint['family'],joint['role']))
    return result


def edge_intervals(model, pid, supports, mates=()):
    """Return uncovered native edge intervals after wood contacts and T&G mates.

    Each declared factory edge is clipped to the current physical perimeter.
    Both panels must retain compatible opposite edges, in the same plane, with
    opposite outward normals. A nearby panel or a ripped edge alone is no mate.
    """
    entry=model.shapes[pid]
    down=cq.Vector(*vector_at(entry['location'],(0,0,-1))).normalized()
    def bottoms(key):
        return [f for f in model.shapes[key]['world'].Faces() if f.geomType()=='PLANE' and f.normalAt().dot(down)>1-1e-5]
    underside=[f for f in entry['world'].Faces() if f.normalAt().dot(down)>1e-5]
    if any(f.geomType()!='PLANE' or f.normalAt().dot(down)<1-1e-5 for f in underside):
        raise StudError('unsupported_measurement','Panel edge checks require a planar underside; sloped or curved underside geometry needs another detail.')
    faces=bottoms(pid)
    if not faces:
        raise StudError('unsupported_measurement','Panel has no planar underside in its declared stock frame.')
    factory=_factory(model,pid,faces);joints=[]
    for mate in mates:
        for a,na,family,role in factory:
            for b,nb,other_family,other_role in _factory(model,mate,bottoms(mate)):
                if family!=other_family or {role,other_role}!={'tongue','groove'} or na.dot(nb)>-1+1e-5:continue
                common=a.intersect(b)
                if _length(common)>1e-7:joints.append(common)
    records=[];uncovered=[]
    for face in faces:
        contacts=[]
        for key in supports:
            for backing in model.shapes[key]['world'].Faces():
                if backing.geomType()=='PLANE' and backing.normalAt().dot(down)<-1+1e-5 and face.distance(backing)<1e-5:
                    contacts.extend(face.intersect(backing).Faces())
        for edge in face.Edges():
            remaining=edge
            for contact in contacts:
                if not remaining.Edges():break
                remaining=remaining.cut(contact)
            wood=edge.Length()-_length(remaining)
            for joint in joints:
                if not remaining.Edges():break
                remaining=remaining.cut(joint)
            missing=_length(remaining);uncovered.extend(remaining.Edges())
            records.append(dict(length=edge.Length(),wood_supported=wood,
                joint_supported=edge.Length()-wood-missing,uncovered=missing,center=list(edge.Center().toTuple())))
    return uncovered,records
