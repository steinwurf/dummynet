from dummynet.v2 import DummyNet


def test_hello():
    net = DummyNet()

    assert net.hello() == "Hello Dummynet v2"


    #local = net.localhost()

    
