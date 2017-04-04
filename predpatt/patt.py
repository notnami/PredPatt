#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""References:

https://universaldependencies.github.io/docs/u/dep/index.html

"""


import itertools
from termcolor import colored
from predpatt.UDParse import DepTriple
#from predpatt import filters
from predpatt import rules as R
from predpatt.UDParse import UDParse

no_color = lambda x,_: x

SUBJ = {'nsubj', 'csubj', 'nsubjpass', 'csubjpass'}
OBJ = {'dobj', 'iobj'}

def gov_looks_like_predicate(e):
    # if e.gov "looks like" a predicate because it has potential arguments
    return e.rel in {'nsubj', 'nsubjpass', 'csubj', 'csubjpass',
                     'dobj', 'iobj', 'ccomp', 'xcomp', 'advcl'}


def argument_names(args):
    """Give arguments alpha-numeric names.

    >>> names = argument_names(range(100))

    >>> [names[i] for i in range(0,100,26)]
    [u'?a', u'?a1', u'?a2', u'?a3']

    >>> [names[i] for i in range(1,100,26)]
    [u'?b', u'?b1', u'?b2', u'?b3']

    """
    # Argument naming scheme: integer -> `?[a-z]` with potentially a number if
    # there more than 26 arguments.
    name = {}
    for i, arg in enumerate(args):
        c = i // 26 if i >= 26 else ''
        name[arg] = '?%s%s' % (chr(97+(i % 26)), c)
    return name

def sort_by_position(x):
    return list(sorted(x, key=lambda y: y.position))


class Token(object):

    def __init__(self, position, text, tag):
        self.position = position
        self.text = text
        self.tag = tag
        self.dependents = None
        self.gov = None
        self.gov_rel = None

    def __repr__(self):
        return '%s/%s' % (self.text, self.position)

    @property
    def isword(self):
        "Check if the token is not punctuation."
        return self.tag != '.'

    def argument_like(self):
        "Does this token look like the root of an argument?"
        return (self.gov_rel in
                {'nmod', 'nmod:npmod', 'nmod:tmod',
                 'nsubj', 'csubj', 'csubjpass', 'dobj', 'iobj'})

    def hard_to_find_arguments(self):
        """Is this potentially the root of an easy predicate, which will have an
        argment?

        """
        return self.gov_rel in {'dep', 'conj', 'acl', 'acl:relcl', 'advcl'}


class Argument(object):

    def __init__(self, root, rules):
        self.root = root
        self.rules = rules
        self.position = root.position
        self.tokens = []

    def __repr__(self):
        return 'Argument(%s)' % self.root

    def copy(self):
        x = Argument(self.root, self.rules[:])
        x.tokens = self.tokens[:]
        return x

    def isclausal(self):
        return self.root.gov_rel in {'ccomp', 'csubj', 'csubjpass', 'xcomp'}

    def phrase(self):
        return ' '.join(x.text for x in self.tokens)

    def coords(self):
        "Argument => list of the heads of the conjunctions within it."
        coords = [self]
        # don't consider the conjuncts of ccomp, csubj and amod
        if self.root.gov_rel not in {'ccomp', 'csubj'}:
            for e in self.root.dependents:
                if e.rel == 'conj':
                    coords.append(Argument(e.dep, [R.m()]))
        return sort_by_position(coords)


class Predicate(object):

    def __init__(self, root, rules, type_='normal'):
        self.root = root
        self.rules = rules
        self.position = root.position
        self.arguments = []
        self.type = type_
        self.tokens = []

    def __repr__(self):
        return 'Predicate(%s)' % self.root

    def copy(self):
        x = Predicate(self.root, self.rules[:])
        x.arguments = [arg.copy() for arg in self.arguments]
        x.type = self.type
        x.tokens = self.tokens[:]
        return x

    def identifier(self):
        """Should-be unique identifier for a predicate-pattern for use in downstream
        applications

        Format:

        pred.{type}.{predicate root}.{argument roots}+

        """
        return 'pred.%s.%s.%s' % (self.type, self.position,
                                  '.'.join(str(a.position) for a in self.arguments))

    def has_subj(self):
        return any(arg.root.gov_rel in SUBJ for arg in self.arguments)

    def subj(self):
        for arg in self.arguments:
            if arg.root.gov_rel in SUBJ:
                return arg.copy()

    def has_obj(self):
        return any(arg.root.gov_rel in OBJ for arg in self.arguments)

    def obj(self):
        for arg in self.arguments:
            if arg.root.gov_rel in OBJ:
                return arg.copy()

    def has_borrow_subj(self):
        return any(isinstance(r, R.borrow_subj) for arg in self.arguments for r in arg.rules)

    def phrase(self):
        return self._format_predicate(argument_names(self.arguments))

    def is_broken(self):
        # empty predicate phrase
        if len(self.tokens) == 0:
            return True

        # empty argument phrase
        for arg in self.arguments:
            if len(arg.tokens) == 0:
                return True

        if self.type == 'poss':
            # incorrect number of arguments
            if len(self.arguments) != 2:
                return True

    def _format_predicate(self, name, C=no_color):
        ret = []
        args = self.arguments

        if self.type == 'poss':
            return ' '.join([name[self.arguments[0]], C('poss', 'yellow'), name[self.arguments[1]]])

        if self.type in {'amod', 'appos'}:
            # Special handling for `amod` and `appos` because the target
            # relation `is/are` deviates from the original word order.
            arg0 = None
            other_args = []
            for arg in self.arguments:
                if arg.root == self.root.gov:
                    arg0 = arg
                else:
                    other_args.append(arg)
            relation = C('is/are', 'yellow')
            if arg0 is not None:
                ret = [name[arg0], relation]
                args = other_args
            else:
                ret = [name[args[0]], relation]
                args = args[1:]

        # Mix arguments with predicate tokens. Use word order to derive a
        # nice-looking name.
        for i, y in enumerate(sort_by_position(self.tokens + args)):
            if isinstance(y, Argument):
                ret.append(name[y])
                if (self.root.gov_rel == 'xcomp' and
                    self.root.tag not in {'VERB', 'ADJ', 'JJ'} and
                    i == 0):
                    ret.append(C('is/are', 'yellow'))
            else:
                ret.append(C(y.text, 'green'))
        return ' '.join(ret)

    def format(self, track_rule, C=no_color, indent='\t'):
        lines = []
        name = argument_names(self.arguments)
        # Format predicate
        rule = ''
        if track_rule:
            rule = ',%s' % ','.join(sorted(map(str, self.rules)))
        lines.append('%s%s%s'
                     % (indent, self._format_predicate(name, C=C),
                        C('%s[%s-%s%s]' % (indent, self.root.text,
                                           self.root.gov_rel, rule),
                          'magenta')))
        # Format arguments
        for arg in self.arguments:
            if (arg.isclausal() and arg.root.gov in self.tokens and self.type == 'normal'):
                s = C('SOMETHING', 'yellow') + ' := ' + arg.phrase()
            else:
                s = C(arg.phrase(), 'green')
            rule = ''
            if track_rule:
                rule = ',%s' % ','.join(sorted(map(str, arg.rules)))
            lines.append('%s%s: %s%s'
                         % (indent*2, name[arg], s,
                            C('%s[%s-%s%s]' % (indent, arg.root.text,
                                               arg.root.gov_rel, rule),
                              'magenta')))
        return '\n'.join(lines)


class PredPattOpts:
    def __init__(self,
                 simple=False,
                 cut=False,
                 resolve_relcl=True,
                 resolve_appos=True,
                 resolve_amod=True,
                 resolve_conj=True,
                 resolve_poss=True,
                 en_relcl_dummy_arg_filter=True,
                 big_args=False):
        self.simple = simple
        self.cut = cut
        self.resolve_relcl = resolve_relcl
        self.resolve_appos = resolve_appos
        self.resolve_amod = resolve_amod
        self.resolve_poss = resolve_poss
        self.resolve_conj = resolve_conj
        self.big_args = big_args
        self.en_relcl_dummy_arg_filter = en_relcl_dummy_arg_filter


def convert_parse(parse):
    "Convert dependency parse on integers into a dependency parse on `Token`s."
    tokens = []
    for i, w in enumerate(parse.tokens):
        tokens.append(Token(i, w, parse.tags[i]))

    def convert_edge(e):
        return DepTriple(gov=tokens[e.gov], dep=tokens[e.dep], rel=e.rel)

    for i, _ in enumerate(tokens):
        tokens[i].gov = (None if i not in parse.governor or parse.governor[i].gov == -1
                         else tokens[parse.governor[i].gov])
        tokens[i].gov_rel = parse.governor[i].rel if i in parse.governor else 'root'
        tokens[i].dependents = list(map(convert_edge, parse.dependents[i]))

    return UDParse(tokens, parse.tags, list(map(convert_edge, parse.triples)))


_PARSER = None

class PredPatt(object):

    def __init__(self, parse, opts=None):
        self.options = opts or PredPattOpts()   # use defaults
        parse = convert_parse(parse)
        self._parse = parse
        self.edges = parse.triples
        self.token = parse.tokens
        self.instances = []
        self.events = None
        self.event_dict = None  # map from token position to `Predicate`
        self.extract()

    @classmethod
    def from_constituency(cls, parse_string, cacheable=True, opts=None):
        """Create PredPatt instance from a constituency parse, which we'll convert to UD
        automatically. [English only]

        """
        from predpatt import Parser
        global _PARSER
        if _PARSER is None:
            _PARSER = Parser.get_instance(cacheable)
        parse = _PARSER.to_ud(parse_string)
        return cls(parse, opts=opts)

    @classmethod
    def from_sentence(cls, sentence, cacheable=True, opts=None):
        """Create PredPatt instance from a sentence (string), which we'll parse and
        convert to UD automatically. [English only]

        """
        from predpatt import Parser
        global _PARSER
        if _PARSER is None:
            _PARSER = Parser.get_instance(cacheable)
        parse = _PARSER(sentence)
        return cls(parse, opts=opts)

    def extract(self):

        # Extract heads of predicates
        events = self.identify_predicate_roots()

        # Create a map from token position to Predicate. This map is used when
        # events need to reference other events.
        self.event_dict = {p.root: p for p in events}

        # Extract heads of arguments
        for e in events:
            e.arguments = self.argument_extract(e)

        events = sort_by_position(self._argument_resolution(events))
        for p in events:
            p.arguments.sort(key = lambda x: x.root.position)
        self.events = events

        # extract predicate and argument phrases
        for p in events:

            self._pred_phrase_extract(p)
            for arg in p.arguments:
                if arg.tokens == []:
                    self._arg_phrase_extract(p, arg)

            if self.options.simple:
                # Simplify predicate's by removing non-core arguments.
                p.arguments = [arg for arg in p.arguments
                               if self._simple_arg(p, arg)]

            # Special cases for predicate conjunctions.
            if p.root.gov_rel == 'conj':
                # pull aux and neg from governing predicate.
                g = self.event_dict.get(p.root.gov)
                if g is not None:
                    for d in g.root.dependents:
                        if d.rel in {'aux', 'neg'}:
                            p.tokens.append(d.dep)
                            p.rules.append(R.pred_conj_borrow_aux_neg(g, d))

                # Post-processing of predicate name for predicate conjunctions
                # involving xcomp.
                if p.root.gov.gov_rel == 'xcomp':
                    g = self._get_top_xcomp(p)
                    if g is not None:
                        for y in g.tokens:
                            if (y != p.root.gov
                                and (y.gov != p.root.gov or y.gov_rel != 'advmod')
                                and y.gov_rel != 'case'):

                                p.tokens.append(y)
                                p.rules.append(R.pred_conj_borrow_tokens_xcomp(g, y))

            if len(p.tokens):
                self.instances.extend(self.expand_coord(p))

        if self.options.resolve_relcl and self.options.en_relcl_dummy_arg_filter:
            for p in self.instances:
                # TODO: this should probably live with other argument filter logic.
                if any(isinstance(r, R.pred_resolve_relcl) for r in p.rules):
                    new = [a for a in p.arguments if a.phrase() not in {'that', 'which', 'who'}]
                    if new != p.arguments:
                        p.arguments = new
                        p.rules.append(R.en_relcl_dummy_arg_filter())

        self._cleanup()
        self._remove_broken_predicates()

    def identify_predicate_roots(self):
        "Predicate root identification."

        roots = {}

        def nominate(root, rule, type_ = 'normal'):
            if root not in roots:
                roots[root] = Predicate(root, [rule], type_=type_)
            else:
                roots[root].rules.append(rule)
            return roots[root]

        for e in self.edges:

            # Punctuation can't be a predicate
            if not e.dep.isword:
                continue

            if self.options.resolve_appos:
                if e.rel == 'appos':
                    nominate(e.dep, R.d(), 'appos')

            if self.options.resolve_poss:
                if e.rel == 'nmod:poss':
                    nominate(e.dep, R.v(), 'poss')

            if self.options.resolve_amod:
                # If resolve amod flag is enabled, then the dependent of an amod
                # arc is a predicate (but only if the dependent is an
                # adjective). We also filter cases where ADJ modifies ADJ.
                #
                # TODO: 'JJ' is not a universal tag. Why do we support it?
                #assert e.dep.tag != 'JJ'
                #if e.rel == 'amod' and e.dep.tag in {'JJ', 'ADJ'} and e.gov.tag not in {'JJ', 'ADJ'}:
                if e.rel == 'amod' and e.dep.tag == 'ADJ' and e.gov.tag != 'ADJ':
                    nominate(e.dep, R.e(), 'amod')

            # Avoid 'dep' arcs, they are normally parse errors.
            # Note: we allow amod, poss, and appos predicates, even with a dep arc.
            if e.gov.gov_rel == 'dep':
                continue

            # If it has a clausal subject or complement its a predicate.
            if e.rel in {'ccomp', 'csubj', 'csubjpass'}:
                nominate(e.dep, R.a1())

            if self.options.resolve_relcl:
                # Dependent of clausal modifier is a predicate.
                if e.rel in {'advcl', 'acl:relcl', 'acl'}:
                    nominate(e.dep, R.b())

            if e.rel == 'xcomp':
                # Dependent of an xcomp is a predicate
                nominate(e.dep, R.a2())

            if gov_looks_like_predicate(e):
                if e.rel == 'ccomp' and e.gov.argument_like():
                    # In this case, e.gov looks more like an argument than a predicate
                    #
                    # For example, declarative context sentences
                    #
                    # We expressed [ our hope that someday the world will know peace ]
                    #                     |                                ^
                    #                    gov ------------ ccomp --------- dep
                    #
                    pass
                elif e.gov.gov_rel == 'xcomp':
                    # TODO: I don't think we need this case.
                    if e.gov.gov is not None and not e.gov.gov.hard_to_find_arguments():
                        nominate(e.gov, R.c())
                else:
                    if not e.gov.hard_to_find_arguments():
                        nominate(e.gov, R.c())

        # Add all conjoined predicates
        q = list(roots.values())
        while q:
            gov = q.pop()
            for e in gov.root.dependents:
                if e.rel == 'conj' and e.dep.isword:
                    q.append(nominate(e.dep, R.f()))

        return sort_by_position(list(roots.values()))

    def argument_extract(self, predicate):
        "Argument identification for predicate."
        arguments = []

        for e in predicate.root.dependents:

            # Most basic arguments
            if e.rel in {'nsubj', 'nsubjpass', 'dobj', 'iobj'}:
                arguments.append(Argument(e.dep, [R.g1(e)]))

            # Add 'nmod' deps as long as the predicate type amod.
            #
            # 'two --> (nmod) --> Zapotec --> (amod) --> Indians'
            # here 'Zapotec' becomes a event token due to amod
            #
            if e.rel.startswith('nmod') and predicate.type != 'amod':
                arguments.append(Argument(e.dep, [R.h1()]))

            # Extract argument token from adverbial phrase.
            #
            # e.g. 'Investors turned away from the stock market.'
            # turned <--(advmod) <-- from <-- (nmod) <-- market
            #
            # [Investors] turned away from [the stock market]
            #
            if e.rel == 'advmod':
                for tr in e.dep.dependents:
                    if tr.rel.startswith('nmod'):
                        arguments.append(Argument(tr.dep, [R.h2()]))

            # Include ccomp for completion of predpatt
            # e.g. 'They refused the offer, the students said.'
            # said <-- (ccomp) <-- refused
            #
            # p.s. amod event token is excluded.
            if e.rel in {'ccomp', 'csubj', 'csubjpass'}:
                arguments.append(Argument(e.dep, [R.k()]))

            if self.options.cut and e.rel == 'xcomp':
                arguments.append(Argument(e.dep, [R.k()]))

        if predicate.type == 'amod':
            arguments.append(Argument(predicate.root.gov, [R.i()]))

        if predicate.type == 'appos':
            arguments.append(Argument(predicate.root.gov, [R.j()]))

        if predicate.type == 'poss':
            arguments.append(Argument(predicate.root.gov, [R.w1()]))
            arguments.append(Argument(predicate.root, [R.w2()]))

        return list(arguments)

    # TODO: It would be better to push the "simple argument" logic into argument
    # id phase, instead of doing it as post-processing.
    def _simple_arg(self, pred, arg):
        "Filter out some arguments to simplify pattern."
        if pred.type == 'poss':
            return True
        if (pred.root.gov_rel in {'amod', 'appos', 'acl', 'acl:relcl'}
            and pred.root.gov == arg.root):
            # keep the post-added argument, which neither directly nor
            # indirectly depends on the predicate root. Say, the governor
            # of amod, appos and acl.
            return True
        if arg.root.gov_rel in SUBJ:
            # All subjects are core arguments, even "borrowed" one.
            return True
        if arg.root.gov_rel in {'nmod', 'nmod:npmod', 'nmod:tmod'}:
            # remove the argument which is a nominal modifier.
            # this condition check must be in front of the following one.
            pred.rules.append(R.p1())
            return False
        if arg.root.gov == pred.root or arg.root.gov.gov_rel == 'xcomp':
            # keep argument directly depending on pred root token,
            # except argument is the dependent of 'xcomp' rel.
            return True
        return False

    def expand_coord(self, predicate):
        """ Expand coordinated arguments.

        e.g. arg11 and arg12 pred arg21 and arg22.
             --> arg11 pred arg21.
             --> arg11 pred arg22.
             --> arg12 pred arg22.
             --> arg12 pred arg22.
        the structure of arg2coord_arg_dict:
            {arg_root: {coord_arg_root1:coord1, coord_arg_root2:coord2}}
        """

        # Don't expand amod
        if not self.options.resolve_conj or predicate.type == 'amod':
            predicate.arguments = [arg for arg in predicate.arguments if arg.tokens]
            if not predicate.arguments:
                return []
            return [predicate]

        # Cleanup (strip before we take conjunctions)
        self._strip(predicate)
        for arg in predicate.arguments:
            self._strip(arg)

        aaa = []
        for arg in predicate.arguments:
            if not arg.tokens:
                continue
            C = []
            for c in arg.coords():
                if not c.tokens:
                    # Extract argument phrase (if we haven't already). This
                    # happens because are haven't processed the subrees of the
                    # 'conj' node in the argument until now.
                    self._arg_phrase_extract(predicate, c)
                C.append(c)
            aaa = [C] + aaa

        expanded = itertools.product(*aaa)

        instances = []
        for args in expanded:
            if not args:
                continue
            predicate.arguments = args
            instances.append(predicate.copy())
        return instances

    def _argument_resolution(self, events):
        "Argument resolution."

        for p in list(events):
            if p.root.gov_rel == 'xcomp':
                if not self.options.cut:
                    # Merge the arguments of xcomp to its gov. (Unlike ccomp, an open
                    # clausal complement (xcomp) shares its arguments with its gov.)
                    g = self._get_top_xcomp(p)
                    if g is not None:
                        # Extend the arguments of event's governor
                        args = [arg.copy() for arg in p.arguments]
                        g.rules.append(R.l())
                        g.arguments.extend(args)
                        # copy arg rules of `event` to its gov's rule tracker.
                        for arg in args:
                            arg.rules.append(R.l())
                        # remove p in favor of it's xcomp governor g.
                        events = [e for e in events if e.position != p.position]

        for p in sort_by_position(events):

            # Add an argument to predicate inside relative clause. The
            # missing argument is rooted at the governor of the `acl`
            # depedency relation (type acl) pointing here.
            if self.options.resolve_relcl and p.root.gov_rel.startswith('acl'):
                new = Argument(p.root.gov, [R.arg_resolve_relcl()])
                p.rules.append(R.pred_resolve_relcl())
                p.arguments.append(new)

            if p.root.gov_rel == 'conj' and not p.has_subj():
                g = self.event_dict.get(p.root.gov)
                if g is not None:
                    if g.has_subj():
                        # If an event governed by a conjunction is missing a
                        # subject, try borrowing the subject from the other
                        # event.
                        new_arg = g.subj().copy()
                        new_arg.rules.append(R.borrow_subj(g, p, 3))
                        p.arguments.append(new_arg)

                    else:
                        # Try borrowing the subject from g's xcomp (if any)
                        g = self._get_top_xcomp(g)
                        if g is not None and g.has_subj():
                            new_arg = g.subj().copy()
                            p.arguments.append(new_arg)
                            new_arg.rules.append(R.borrow_subj(g, p, 4))

            if p.root.gov_rel == 'advcl' and not p.has_subj():
                g = self.event_dict.get(p.root.gov)
                if g is not None and g.has_subj():
                    new_arg = g.subj().copy()
                    new_arg.rules.append(R.borrow_subj(g, p, 6))
                    p.arguments.append(new_arg)

            if p.root.gov_rel == 'conj':
                g = self.event_dict.get(p.root.gov)
                if g is not None:
                    # Coordinated appositional modifers share the same subj.
                    if p.root.gov_rel == 'amod':
                        p.arguments.append(Argument(g.root.gov, [R.o()]))
                    elif p.root.gov_rel == 'appos':
                        p.arguments.append(Argument(g.root.gov, [R.p()]))

        for p in sort_by_position(events):
            if p.root.gov_rel == 'xcomp':
                if self.options.cut:
                    for g in self.parents(p):
                        # Subject of an xcomp is most likely to come from the
                        # object of the governing predicate.

                        if g.has_obj():
                            # "I like you to finish this work"
                            #      ^   ^       ^
                            #      g  g.obj    p
                            new_arg = g.obj().copy()
                            new_arg.rules.append(R.cut_borrow_obj(g, g.obj()))
                            p.arguments.append(new_arg)
                            break

                        elif g.has_subj():
                            # "I  'd   like to finish this work"
                            #  ^         ^       ^
                            #  g.subj    g       p
                            new_arg = g.subj().copy()
                            new_arg.rules.append(R.cut_borrow_subj(g, g.subj()))
                            p.arguments.append(new_arg)
                            break

                        elif g.root.gov_rel in {'amod', 'acl', 'acl:relcl'}:
                            # PredPatt recognizes structures which are shown to be accurate .
                            #                         ^                  ^      ^
                            #                       g.subj               g      p
                            new_arg = Argument(g.root.gov, [R.cut_borrow_other(g, g.root.gov)])
                            p.arguments.append(new_arg)
                            break

        for p in sort_by_position(events):

            # Note: The following rule improves coverage a lot in Spanish and
            # Portuguese. Without it, miss a lot of arguments.
            if (not p.has_subj()
                and p.type == 'normal'
                and p.root.gov_rel not in {'csubj', 'csubjpass'}
                and not p.root.gov_rel.startswith('acl')
            ):
                g = self.event_dict.get(p.root.gov)
                if g is not None:
                    if g.has_subj():
                        new_arg = g.subj().copy()
                        new_arg.rules.append(R.borrow_subj(g, p, 1))
                        p.arguments.append(new_arg)
                    else:
                        # Still no subject. Try looking at xcomp of conjunction root.
                        g = self._get_top_xcomp(p)
                        if g is not None and g.has_subj():
                            p.arguments.append(g.subj().copy())
                            p.rules.append(R.borrow_subj(g, p, 2))

        return list(events)

    def _pred_phrase_extract(self, predicate):
        """Collect tokens for pred phrase in the dependency
        subtree of pred root token.

        """
        assert predicate.tokens == []
        predicate.tokens.extend(self.subtree(predicate.root,
                                             lambda e: self.__pred_phrase(predicate, e)))

        if not self.options.simple:
            for arg in predicate.arguments:
                # Hoist case phrases in arguments into predicate phrase.
                #
                # Exception: do no extract case phrase from amod, appos and
                # relative clauses.
                #
                # e.g. 'Mr. Vinken is chairman of Elsevier , the Dutch publisher .'
                #       'Elsevier' is the arg phrase, but 'of' shouldn't
                #       be kept as a case token.
                #
                if (predicate.root.gov_rel not in {'amod', 'appos', 'acl', 'acl:relcl'}
                    or predicate.root.gov != arg.root):
                    for e in arg.root.dependents:
                        if e.rel == 'case':
                            arg.rules.append(R.o2())
                            predicate.tokens.extend(self.subtree(e.dep))
                            predicate.rules.append(R.n6(e.dep))

    def __pred_phrase(self, pred, e):
        """Helper routine for predicate phrase extraction.

        This functions is used when determining which edges to traverse when
        extracting predicate phrases. We add the dependent of each edge we
        traverse.

        Note: This function appends rules to predicate as a side-effect.

        """

        if e.dep in {a.root for a in pred.arguments}:
            # pred token shouldn't be argument root token.
            pred.rules.append(R.n2(e.dep))
            return False

        if e.dep in {p.root for p in self.events} and e.rel != 'amod':
            # pred token shouldn't be other pred root token.
            pred.rules.append(R.n3(e.dep))
            return False

        if e.rel in {'ccomp', 'csubj', 'advcl', 'acl', 'acl:relcl', 'nmod:tmod',
                     'parataxis', 'appos', 'dep'}:
            # pred token shouldn't be a dependent of any rels above.
            pred.rules.append(R.n4(e.dep))
            return False

        if (e.gov == pred.root or e.gov.gov_rel == 'xcomp') and e.rel in {'cc', 'conj'}:
            # pred token shouldn't take conjuncts of pred
            # root token or xcomp's dependent.
            pred.rules.append(R.n5(e.dep))
            return False

        if self.options.simple:
            # Simple predicates don't have nodes governed by advmod or aux.
            if e.rel == 'advmod':
                pred.rules.append(R.q())
                return False
            elif e.rel == 'aux':
                pred.rules.append(R.r())
                return False

        pred.rules.append(R.n1(e.dep))
        return True

    def _arg_phrase_extract(self, pred, arg):
        """Collect tokens for arg phrase in the dependency
        subtree of pred root token and split the case phrase
        from the subtree.

        """
        assert arg.tokens == []
        arg.tokens.extend(self.subtree(arg.root,
                                       lambda e: self.__arg_phrase(pred, arg, e)))

    def __arg_phrase(self, pred, arg, e):
        """Helper routine for determining which tokens to extract for the argument
        phrase from the subtree rooted at argument's root token. Rationales are
        provided as a side-effect.

        """
        if self.options.big_args:
            return True

        if e.dep == pred.root:
            # arg token shouldn't be the pred root token.
            arg.rules.append(R.o3())
            return False

        # Case tokens are added to predicate, not argument.
        if e.gov == arg.root and e.rel == 'case':
            return False

        # Don't include relative clauses, appositives, the junk label (dep).
        if e.rel in {'acl', 'acl:relcl', 'dep', 'appos'}:
            arg.rules.append(R.o4())
            return False

        # Direct dependents of the predicate root of the follow types shouldn't
        # be added the predicate phrase.
        if (arg.root == pred.root.gov
            and e.rel in {'nsubj', 'dobj', 'iobj', 'csubj', 'csubjpass', 'neg',
                          'aux', 'advcl', 'auxpass', 'ccomp', 'cop', 'mark',
                          'mwe', 'parataxis'}):
            arg.rules.append(R.o4())
            return False

        # Don't take embedded advcl for ccomp arguments.
        if arg.root.gov_rel == 'ccomp' and e.rel == 'advcl':
            arg.rules.append(R.o4())
            return False

        # Don't take embedded ccomps from clausal subjects arguments
        if arg.root.gov_rel in {'csubj', 'csubjpass'} and e.rel == 'ccomp':
            arg.rules.append(R.o4())
            return False

        # Nonclausal argument types should avoid embedded advcl and ccomp
        if arg.root.gov_rel not in {'ccomp', 'csubj', 'csubjpass'} and e.rel in {'advcl', 'ccomp'}:
            arg.rules.append(R.o4())
            return False

        if self.options.resolve_conj:

            # Remove top-level conjunction tokens if work expanding conjunctions.
            if e.gov == arg.root and e.rel in {'cc', 'cc:preconj'}:
                arg.rules.append(R.o5())
                return False

            # Argument shouldn't include anything from conjunct subtree.
            if e.gov == arg.root and e.rel == 'conj':
                arg.rules.append(R.o6())
                return False

        # If non of the filters fired, then we accept the token.
        arg.rules.append(R.o1())
        return True

    def _cleanup(self):
        """Cleanup operations: Sort instances and the arguments by text order. Remove
        certain punc and mark tokens.

        """
        self.instances = sort_by_position(self.instances)
        for p in self.instances:
            p.arguments = sort_by_position(p.arguments)
            self._strip(p)
            for arg in p.arguments:
                self._strip(arg)

    def _strip(self, thing):
        """Simplify expression by removing ``punct``, ``cc``, and ``mark`` from the
        begining and end of the set of ``tokens``.

        For example,
        Trailing punctuation: 'said ; .' -> 'said'
        Function words: 'to shore up' -> 'shore up'

        """
        if self.options.big_args:
            return

        tokens = sort_by_position(thing.tokens)
        orig_len = len(tokens)
        rels = {'mark', 'cc', 'punct'}

        protected = set()
        #def protect_open_close(x, i, open_, close):
        #    if x.text == open_:
        #        J = -1
        #        for j in range(i, len(tokens)):
        #            if tokens[j].text == close:
        #                J = j
        #        if J != -1:
        #            # only protects the open and close tokens if the both appear
        #            # in the span.
        #            protected.add(x.position)
        #            protected.add(tokens[J].position)
        #for i, x in enumerate(tokens):
        #    protect_open_close(x, i, '``', "''")
        #    protect_open_close(x, i, '(', ')')
        #    protect_open_close(x, i, '[', ']')
        #    protect_open_close(x, i, '"', '"')
        #    protect_open_close(x, i, "'", "'")
        #    protect_open_close(x, i, '-LRB-', '-RRB-')
        #    protect_open_close(x, i, '-LCB-', '-RCB-')

        try:
            # prefix
            while tokens[0].gov_rel in rels and tokens[0].position not in protected:
                if (isinstance(thing, Argument)
                    and tokens[0].gov_rel == 'mark'
                    and tokens[1].tag == 'VERB'):
                    break
                tokens.pop(0)
            # suffix
            while tokens[-1].gov_rel in rels and tokens[-1].position not in protected:
                tokens.pop()
        except IndexError:
            tokens = []
        # remove repeated punctuation from the middle (happens when we remove an appositive)
        tokens = [tk for i, tk in enumerate(tokens)
                  if ((tk.gov_rel != 'punct' or (i+1 < len(tokens) and tokens[i+1].gov_rel != 'punct'))
                      or tk.position in protected)]
        if orig_len != len(tokens):
            thing.rules.append(R.u())
        thing.tokens = tokens

    def _remove_broken_predicates(self):
        """Remove broken predicates.
        """
        instances = []
        for p in self.instances:
            if p.is_broken():
                continue
            instances.append(p)
        self.instances = instances

    @staticmethod
    def subtree(s, follow = lambda _: True):
        """Breadth-first iterator over nodes in a dependency tree.

        - follow: (function) takes an edge and returns true if we should follow
          the edge.

        - s: initial state.

        """
        q = [s]
        while q:
            s = q.pop()
            yield s
            q.extend(e.dep for e in s.dependents if follow(e))

    def _get_top_xcomp(self, predicate):
        """
        Find the top-most governing xcomp predicate, if there are no xcomps
        governors return current predicate.
        """
        c = predicate.root.gov
        while c is not None and c.gov_rel == 'xcomp' and c in self.event_dict:
            c = c.gov
        return self.event_dict.get(c)

    def parents(self, predicate):
        "Iterator over the chain of parents (governing predicates)."
        c = predicate.root.gov
        while c is not None:
            if c in self.event_dict:
                yield self.event_dict[c]
            c = c.gov

    def pprint(self, color=False, track_rule=True):
        "Pretty-print extracted predicate-argument tuples."
        C = colored if color else no_color
        return '\n'.join(p.format(C=C, track_rule=track_rule) for p in self.instances)
