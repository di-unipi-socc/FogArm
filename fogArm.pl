:-dynamic deployment/3.
:-dynamic application/2.
:-dynamic service/4.
:-dynamic s2s/4.
:-dynamic link/4.
:-dynamic node/4.

:- consult('placers/placer.pl').
:- consult('fogBrainX.pl').

writeDeployment(File,D) :-
    open(File,write,Out),
    write(Out, ':-dynamic deployment/3'), write(Out,'.\n'),
    write(Out, ':-dynamic application/2'), write(Out,'.\n'),
    write(Out, ':-dynamic service/4'), write(Out,'.\n'),
    write(Out, ':-dynamic s2s/4'), write(Out,'.\n'),
    write(Out, ':-dynamic node/4'), write(Out,'.\n'),
    write(Out, ':-dynamic link/4'), write(Out,'.\n'),
    write(Out,D), write(Out,'.\n'),
    close(Out).

fogArmX(ToAdd, ToRemove, ToMigrate) :-
    source_file(fogArmX(_,_,_), Filename),
    string_concat(Path, 'fogArmX.pl', Filename),
    application(A,_),
    string_concat(Path, '.tmp/.placements/.', TmpPath),
    term_string(A, App),
    string_concat(TmpPath, App, File),
    exists_file(File), consult(File),
    fogArmX(A, ToAdd, ToRemove, ToMigrate),
    deployment(A,NewP,NewAlloc),
    writeDeployment(File, deployment(A,NewP,NewAlloc)).

fogArmX(ToAdd, ToRemove, ToMigrate) :-
    source_file(fogArmX(_,_,_), Filename),
    string_concat(Path, 'fogArmX.pl', Filename),
    application(A,_),
    string_concat(Path, '.tmp/.placements/.', TmpPath),
    term_string(A, App),
    string_concat(TmpPath, App, File),
    \+ exists_file(File),
    fogArmX(A, ToAdd, ToRemove, ToMigrate),
    deployment(A,NewP,NewAlloc),
    writeDeployment(File, deployment(A,NewP,NewAlloc)).

fogArmX(A, ToAdd, [], []) :-
    \+ deployment(A,_,_),
    fogBrainX(A, TmpToAdd),
    %placementX(A, TmpToAdd),
    findall(on(NewS,Node), (member(on(S,N),TmpToAdd), term_string(N, Node), term_string(S, NewS)), ToAdd).

fogArmX(A, ToAdd, ToRemove, ToMigrate) :-
    deployment(A,OldP,_),
    fogBrainX(A, NewP),
    %placementX(A, NewP),
    deployment(A,NewP,_),
    findall(on(NewS,NewNode), (member(on(S,NewN),NewP), \+ member(on(S,_),OldP), term_string(NewN, NewNode), term_string(S, NewS)), ToAdd),
    findall(on(NewS,OldNode), (member(on(S,OldN),OldP), \+member(on(S,_),NewP), term_string(OldN, OldNode), term_string(S, NewS)), ToRemove),
    findall(mv(NewS,OldNode,NewNode), (member(on(S,OldN),OldP), member(on(S,NewN),NewP), dif(OldN, NewN), term_string(NewN, NewNode), term_string(OldN, OldNode), term_string(S, NewS)), ToMigrate).

placementX(A, P) :-
    \+ deployment(A,_,_),
    application(A,Services), placement(Services,[],([],[]),P),
    allocatedResources(P,Alloc), assert(deployment(A,P,Alloc)).
placementX(A, P) :-
    deployment(A,_,OldAlloc),
    application(A,Services), placement(Services,[],OldAlloc,P),
    allocatedResources(P,Alloc), retract(deployment(A,_,_)), assert(deployment(A,P,Alloc)).