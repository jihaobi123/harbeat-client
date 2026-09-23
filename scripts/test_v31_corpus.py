import unittest
from build_v31_corpus import select
class Selection(unittest.TestCase):
 def row(self,i,bpm=90,v=.5,sha=None):return dict(track_id=str(i),sha=sha or str(i),eligible=True,bpm=bpm,vocalCoverage=v,style=[dict(style='Trap')])
 def test_keeps_originals_and_deduplicates_content(self):
  rows=[self.row(1),self.row(2,140),self.row(3,120,sha='1'),self.row(4,90,0)]
  result=select(rows,['1'],3);self.assertEqual(result[0]['track_id'],'1');self.assertEqual(len({r['sha'] for r in result}),3)
 def test_ignores_transition_success_when_selecting(self):
  rows=[self.row(i,80+i*5) for i in range(6)]
  before=select(rows,['0'],4)
  for r in rows:r['feasible']=r['track_id']=='1'
  self.assertEqual(before,select(rows,['0'],4))
 def test_fails_explicitly_when_insufficient_or_seed_missing(self):
  with self.assertRaises(ValueError):select([self.row(1)],['missing'],2)
  with self.assertRaises(ValueError):select([self.row(1)],['1'],2)
if __name__=='__main__':unittest.main()
