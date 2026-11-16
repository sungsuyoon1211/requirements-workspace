import copy
import unittest
import context_engine as ce

class ContextTest(unittest.TestCase):
    def context(self):
        return {'project':{'commonRules':'관리자 승인'},'baseRequirement':{},'previousDraft':{'draft':{'title':'환불','expected':'승인 후 환불'},'gaps':['수수료 미정']},'sources':[],'existingRequirements':[], 'conversation':[{'role':'user','text':'환불 수수료 규칙 확인'}]}, {'id':'NEW','projectId':'P','owner':'alice','messages':[]}

    def test_old_chain_retrieval_and_exact_source_offsets(self):
        c,item=self.context();item['continuedFrom']='OLD'
        fact='환불 수수료는 고객이 부담하지 않고 판매자가 부담한다.'
        parent={'id':'OLD','projectId':'P','owner':'alice','messages':[{'role':'user','text':fact}]+[{'role':'assistant','text':'다른 업무 '+str(i)} for i in range(2000)]}
        c['sources']=[{'id':'SRC','name':'정책','text':'다른 업무. '*40000+fact}]
        before=copy.deepcopy(c);p=ce.pack(c,item,[parent],budget=14000)
        self.assertEqual(p['previousDraft'],c['previousDraft']);self.assertEqual(p['project'],c['project'])
        self.assertLess(ce.size(p),14500);self.assertIn(fact,str(p))
        self.assertTrue(any(x['locator'].startswith('OLD:') for x in p['retrievedContext']))
        for s in p['sources']: self.assertEqual(s['text'],c['sources'][0]['text'][s['start']:s['end']])
        self.assertEqual(c,before);self.assertGreater(p['contextCoverage']['omittedChunks'],0)

    def test_private_chain_and_cycle(self):
        c,item=self.context();item['continuedFrom']='SECRET'
        for owner,project in [('bob','P'),('alice','OTHER')]:
            rows,complete=ce.prior_history(item,[{'id':'SECRET','projectId':project,'owner':owner,'messages':[{'text':'secret'}]}])
            self.assertEqual(rows,[]);self.assertFalse(complete)
        rows,complete=ce.prior_history(item,[{'id':'SECRET','projectId':'P','owner':'alice','continuedFrom':'NEW','messages':[]}])
        self.assertFalse(complete)

    def test_full_context_and_oversized_core_never_clipped(self):
        c,item=self.context();self.assertEqual(ce.pack(c,item,[])['contextCoverage']['mode'],'full')
        c['previousDraft']['draft']['expected']='확정 내용 '*10000
        p=ce.pack(c,item,[],budget=12000)
        self.assertEqual(p['previousDraft'],c['previousDraft']);self.assertTrue(p['contextCoverage']['coreExceedsBudget'])

    def test_updated_source_not_stale(self):
        c,item=self.context();c['sources']=[{'id':'S','name':'정책','text':'수수료 미정'}]
        ce.pack(c,item,[]);c['sources'][0]['text']='수수료 판매자 부담'
        self.assertEqual(ce.pack(c,item,[])['sources'][0]['text'],'수수료 판매자 부담')
