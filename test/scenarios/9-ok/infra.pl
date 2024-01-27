:-dynamic node/4.
:-dynamic link/4.

node(node1-garr-ct1,[], 12,[]).
node(node2-garr-ct1,[], 10,[]).
node(node3-garr-ct1,[], 8,[]).
link(node1-garr-ct1,node2-garr-ct1,1,30).
link(node2-garr-ct1,node1-garr-ct1,1,30).
link(node1-garr-ct1,node3-garr-ct1,1,30).
link(node3-garr-ct1,node1-garr-ct1,1,30).
link(node2-garr-ct1,node3-garr-ct1,1,30).
link(node3-garr-ct1,node2-garr-ct1,1,30).