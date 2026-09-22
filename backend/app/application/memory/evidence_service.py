"""Read authorized evidence and issue scope-bound receipts for actual content."""

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import secrets


from backend.app.application.memory.service import MemoryService
from backend.app.core.errors import SerenitaError
from backend.app.schemas.memory.append import (
    MemoryReference,
)
from backend.app.schemas.memory.requests import MemoryReadRequest
from backend.app.application.memory.evidence_scope import MemoryEvidenceScope


def fail(code, message, kind="invalid_input"):
    raise SerenitaError(kind, code, message)


@dataclass(frozen=True)
class EvidenceBinding:
    actor: str
    member: str
    session_id: str | None
    task_id: str
    object_reads: dict = field(repr=False)
    coverage_reads: dict = field(repr=False)
    scope: MemoryEvidenceScope = field(repr=False)
    issuer: object = field(repr=False)
    change_reads: dict = field(default_factory=dict, repr=False)


class MemoryEvidenceService:
    def __init__(self, memory=None):
        self.memory = memory or MemoryService()
        self.members = self.memory.members
        self._secret = secrets.token_bytes(32)
        self._issuer = object()


    def _read_signature(self, binding, kind, value):
        payload = json.dumps([binding.actor, binding.member, binding.session_id, binding.task_id, kind, digest(value)], separators=(",", ":"))
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    def bind(self, scope, observations=()):
        """Bind actual reads to a caller-provided identity, without plugin dependencies."""
        if not isinstance(scope, MemoryEvidenceScope) or not scope.member_id or not scope.task_id.strip():
            fail('MEMORY_TASK_SCOPE_INVALID', '记忆读取必须绑定实际成员和任务标识。', 'forbidden')
        binding = EvidenceBinding(scope.account_id, scope.member_id, scope.session_id, scope.task_id,
            {}, {}, scope, self._issuer)
        for observation in observations:
            if observation.get('name') not in {'read_memory', 'read_memory_statistics', 'read_memory_graph'} or not observation.get('call_id'):
                continue
            output = observation.get('output')
            if isinstance(output, dict) and output.get('member_id') == binding.member:
                self._adopt_read(binding, output)
        return binding

    def bind_prepared_input(self, scope, results):
        """Adopt signed reads from a successful fixed-stage request."""
        binding = self.bind(scope)
        for output in results:
            if output.get('member_id') != binding.member:
                fail('MEMORY_TASK_SCOPE_MISMATCH', '阶段输入与当前成员不一致。', 'forbidden')
            self._adopt_read(binding, output)
        return binding

    def revalidate_frozen_reads(self, scope, reads):
        """Check live access and immutable content before reissuing scoped receipts."""
        binding = self.bind(scope)
        actor, member = scope.account_id, scope.member_id
        live_cutoff = self.memory.repository.snapshot(actor, member)['record_cutoff']
        checked_reads = deepcopy(reads)
        for result in checked_reads:
            expected = {reference_key(object_reference(row)): row for row in result.get('objects', [])}
            references = [object_reference(row) for row in result.get('objects', [])]
            for offset in range(0, len(references), 100):
                actual = self.memory.repository.read_facts(actor, member,
                    references[offset:offset + 100], record_cutoff=live_cutoff)
                for row in actual['objects']:
                    prior = expected[reference_key(object_reference(row))]
                    if persistent_object_digest(row) != persistent_object_digest(prior):
                        fail('MEMORY_CHECKPOINT_INPUT_CHANGED', '固定记忆对象与当前获授权内容不一致。')
            sources = result.get('change_sources', [])
            if sources:
                actual = self.memory.repository.evidence.read_changes(actor, member,
                    [row['reference'] for row in sources], sources=True)
                if actual != sources:
                    fail('MEMORY_SOURCE_NOT_READ', '固定业务依据与当前获授权资料不一致。')
            if 'record_cutoff' in result:
                result['record_cutoff'] = live_cutoff
            if result.get('read_query') and 'record_cutoff' in result['read_query']:
                result['read_query']['record_cutoff'] = live_cutoff
            # Receipt creation owns coverage construction and signing together.
            result['object_read_receipts'] = [{'reference': object_reference(row),
                'read_receipt': self._read_signature(binding, 'object', row)} for row in result.get('objects', [])]
            result['change_read_receipts'] = [{'source_key': row['source_key'],
                'read_receipt': self._read_signature(binding, 'change', row)} for row in sources]
            if result.get('read_coverage') is not None:
                coverage = result['read_coverage']
                coverage['record_cutoff'] = live_cutoff
                if coverage.get('query') and 'record_cutoff' in coverage['query']:
                    coverage['query']['record_cutoff'] = live_cutoff
                result['coverage_read_receipt'] = self._read_signature(binding, 'coverage', coverage)
        return checked_reads

    def _adopt_read(self, binding, output):
        for source in output.get('change_sources', []):
            receipt=next((r.get('read_receipt') for r in output.get('change_read_receipts', [])
                if r.get('source_key')==source['source_key']), None)
            if isinstance(receipt,str) and hmac.compare_digest(receipt,self._read_signature(binding,'change',source)):
                binding.change_reads[source['source_key']]=deepcopy(source)

        actual_objects = {reference_key(object_reference(row)): row for row in output.get("objects", [])
                          if isinstance(row, dict) and row.get("object_type")}
        for receipt in output.get("object_read_receipts", []):
            key = reference_key(receipt["reference"])
            row = actual_objects.get(key)
            if row is not None and hmac.compare_digest(receipt["read_receipt"], self._read_signature(binding, "object", row)):
                binding.object_reads.setdefault(key, set()).add(persistent_object_digest(row))
        coverage = output.get("read_coverage")
        receipt = output.get("coverage_read_receipt")
        if coverage is not None and isinstance(receipt, str) and hmac.compare_digest(receipt, self._read_signature(binding, "coverage", coverage)):
            binding.coverage_reads[receipt] = deepcopy(coverage)
    def require_binding(self, actor, member, binding):
        if not isinstance(binding, EvidenceBinding) or binding.issuer is not self._issuer or (actor, member) != (binding.actor, binding.member):
            fail("MEMORY_RUNTIME_BINDING_REQUIRED", "记忆能力必须经当前任务的可信运行时绑定。", "forbidden")

    def receipts(self, result, binding):
        """Sign actual authorized service results in their bound scope."""
        self.require_binding(binding.actor, binding.member, binding)
        from backend.app.repositories.memory.sources.evidence import change_source
        result['change_sources']=[change_source(row) for row in result.get('business_changes', [])]
        result['change_read_receipts']=[{'source_key':row['source_key'],'read_receipt':self._read_signature(binding,'change',row)}
            for row in result['change_sources']]
        result["object_read_receipts"] = [{"reference": object_reference(row), "read_receipt": self._read_signature(binding, "object", row)}
            for row in result["objects"]]
        if result.get("record_cutoff") is not None:
            result["read_coverage"] = {"record_cutoff": result["record_cutoff"], "query": result.get("read_query"),
                "references": [item["reference"] for item in result["object_read_receipts"]],
                "coverage": deepcopy(result.get("coverage", {})),
                "unread": deepcopy(result.get("unread", [])), "gaps": deepcopy(result.get("gaps", [])),
                "next_cursor": result.get("next_cursor"), "complete": not result.get("unread") and result.get("next_cursor") is None}
            result["coverage_read_receipt"] = self._read_signature(binding, "coverage", result["read_coverage"])
        return result

    def require_read_objects(self, actor, member, references, *, binding, record_cutoff=None, require_sources=True):
        self.require_binding(actor, member, binding)
        validated = [self.memory._validate(MemoryReference, item.model_dump(mode="json") if hasattr(item, "model_dump") else item).model_dump(mode="json") for item in references]
        requested = list({reference_key(item): item for item in validated}.values())
        if not requested:
            return {}
        actual = {}
        for index in range(0, len(requested), 100):
            result = self.memory.repository.read_facts(actor, member, requested[index:index + 100], record_cutoff=record_cutoff)
            for row in result["objects"]:
                key = reference_key(object_reference(row))
                if persistent_object_digest(row) not in binding.object_reads.get(key, set()):
                    fail("MEMORY_OBJECT_NOT_READ", "所采用对象必须在当前轮次实际读取，且内容与指定记录截点一致。", "forbidden")
                actual[key] = row
        if require_sources:
            from backend.app.schemas.memory.evidence import source_key
            references = self.memory.repository.evidence.source_references(actor, member, actual.values())
            self.require_change_reads(actor, member, {source_key(ref) for ref in references}, binding=binding)
        return actual

    def read_changes(self, actor, member, references, *, binding):
        self.require_binding(actor, member, binding)
        sources = self.memory.repository.evidence.read_changes(actor, member, references, sources=True)
        result = {'member_id': member, 'objects': [], 'change_sources': sources,
            'change_read_receipts': [{'source_key': source['source_key'],
                'read_receipt': self._read_signature(binding, 'change', source)} for source in sources]}
        self._adopt_read(binding, result)
        return result

    def require_change_reads(self, actor, member, keys, *, binding):
        self.require_binding(actor, member, binding)
        expected = {}
        for key in keys:
            source = binding.change_reads.get(key)
            if source is None:
                fail('MEMORY_SOURCE_NOT_READ', '采用的业务变更必须在当前阶段实际读取。', 'forbidden')
            expected[key] = source
        actual = self.memory.repository.evidence.read_changes(actor, member,
            [source['reference'] for source in expected.values()], sources=True)
        sources = {source['source_key']: source for source in actual}
        if sources != expected:
            fail('MEMORY_SOURCE_NOT_READ', '业务依据与当前阶段实际读取的内容不一致。', 'forbidden')
        return sources

    def read(self, actor, member, values, *, binding):
        self.require_binding(actor, member, binding)
        request = self.memory._validate(MemoryReadRequest, values)
        result = self.memory.query(actor, member, request.model_dump(mode="json"))
        result["read_query"] = request.model_dump(mode="json")
        return self.receipts(result, binding)

    def read_prepared(self, actor, member, values, *, binding):
        """Issue receipts for the exact background facts checked at this cutoff."""
        self.require_binding(actor, member, binding)
        request = self.memory._validate(MemoryReadRequest, values)
        result = self.memory.repository.read_facts(actor, member,
            [ref.model_dump(mode='json') for ref in request.references], record_cutoff=request.record_cutoff)
        result['read_query'] = request.model_dump(mode='json')
        return self.receipts(result, binding)


from backend.app.domain.memory.references import object_reference, reference_key
from backend.app.core.values import strict_digest as digest
from backend.app.repositories.memory.reading.object_projection import persistent_object_digest
