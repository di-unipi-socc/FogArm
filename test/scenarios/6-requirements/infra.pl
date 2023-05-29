:-dynamic node/4.
:-dynamic link/4.

node(node1-garr-ct1,[], 6,[]).
node(node2-garr-ct1,[], 2,[]).
node(node3-garr-ct1,[], 6,[]).
link(node1-garr-ct1,node2-garr-ct1,50,20).
link(node2-garr-ct1,node1-garr-ct1,50,20).
link(node1-garr-ct1,node3-garr-ct1,50,20).
link(node3-garr-ct1,node1-garr-ct1,50,20).
link(node2-garr-ct1,node3-garr-ct1,50,20).
link(node3-garr-ct1,node2-garr-ct1,50,20).