import pytest
from pydantic import BaseModel, Field
from backend.app.agent_runtime.tools.parameters import model_parameters, validate_parameters

@pytest.mark.parametrize('schema,value',[
    ({'anyOf':[{'type':'string'},{'type':'null'}],'maxLength':3},'long'),
    ({'oneOf':[{'type':'integer'},{'type':'number'}]},2),
    ({'type':'array','uniqueItems':True},[1,1]),
    ({'type':'string','pattern':'^[A-Z]+$'},'lower'),
    ({'type':'object','dependentRequired':{'a':['b']}},{'a':1}),
    ({'allOf':[{'type':'object','properties':{'a':{'type':'number'}}}],'unevaluatedProperties':False},{'a':1,'extra':True}),
    ({'type':['number','null'],'exclusiveMinimum':0},0),
])
def test_composition_and_sibling_constraints_are_enforced(schema,value):
    with pytest.raises(ValueError):validate_parameters(value,schema,label='参数')


def test_reference_siblings_keep_their_constraints_and_description():
    class Child(BaseModel):
        value: str
    class Parent(BaseModel):
        child: Child=Field(description='字段位置的说明',json_schema_extra={'maxProperties':1})
    schema=model_parameters(Parent)
    assert schema['properties']['child']['description']=='字段位置的说明'
    validate_parameters({'child':{'value':'ok'}},schema,label='参数')
    with pytest.raises(ValueError):validate_parameters({'child':{'value':'ok','extra':'x'}},schema,label='参数')
