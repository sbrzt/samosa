import io

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from conftest import VOCABULARY as VOCAB, graph, zoo
from scripts import align
from scripts.common import EX, load_yaml

VOC = "http://example.com/voc/"
V = lambda name: URIRef(VOC + name)
E = lambda name: URIRef(EX + name)
PREFIXES = {"voc": VOC}


def test_expand_curies_local_terms_and_iris():
    assert align.expand("voc:Creature", PREFIXES) == VOC + "Creature"
    assert align.expand(" :Animal ", PREFIXES) == EX + "Animal"
    assert align.expand("http://x.org/A", PREFIXES) == "http://x.org/A"


def test_expand_rejects_unknown_prefixes(capsys):
    with pytest.raises(SystemExit):
        align.expand("foaf:Person", PREFIXES)
    assert "Add it to prefixes.yaml" in capsys.readouterr().out


def test_aliases_map_local_names_to_targets():
    data = {"glossary": [{"term": "has rights", "type": "ObjectProperty", "align_to": "voc:rights"},
                         {"term": "animal", "type": "Class", "align_to": ""},
                         {"term": "thing", "type": "Class", "align_to": "http://example.org/"}]}
    assert align.aliases(data, PREFIXES) == {"hasrights": "rights"}


def test_load_prefixes(project):
    assert align.load_prefixes() == PREFIXES
    (project / "prefixes.yaml").unlink()
    assert align.load_prefixes() == {}


def test_refactor_query_rewrites_only_whole_local_terms():
    query = "SELECT * WHERE { ?a :eats ?b ; :EatsMore ?c ; <https://www.example.org/eats> ?d ; voc:eats ?e }"
    out = align.refactor_query(query, {"eats": VOC + "feedsOn"})
    assert out.count(f"<{VOC}feedsOn>") == 2
    assert ":EatsMore" in out and "voc:eats" in out


def test_describe_follows_blank_nodes():
    g = graph("voc:x rdfs:comment [ rdfs:label [ rdfs:label \"deep\" ] ] . voc:y rdfs:label \"other\" .")
    triples = list(align.describe(g, V("x")))
    assert len(triples) == 3 and Literal("deep") in {o for _, _, o in triples}


def test_vocabulary_sources(project, capsys):
    assert (V("Creature"), RDFS.label, Literal("creature", lang="en")) in align.vocabulary(VOC + "Creature", PREFIXES)
    assert align.vocabulary("http://unknown.org/x", PREFIXES) is None
    assert len(align.vocabulary(EX + "Animal", PREFIXES)) == 0  # no current model yet
    empty = align.vocabulary("http://other.org/x", {"oth": "http://other.org/"})  # fetch fails: no network
    assert len(empty) == 0 and "cannot load vocabulary 'oth'" in capsys.readouterr().out


def test_vocabulary_of_local_terms_is_the_current_model(project):
    (project / "project").mkdir()
    (project / "project" / "tbox.ttl").write_text(graph(":Animal a owl:Class .").serialize(format="turtle"))
    assert (E("Animal"), RDF.type, URIRef("http://www.w3.org/2002/07/owl#Class")) in align.vocabulary(EX + "Animal", {})


def test_register_prefixes_appends_missing_namespaces(project):
    g = Graph()
    g.bind("oth", "http://other.org/ns#")
    g.add((URIRef("http://other.org/ns#x"), RDFS.label, Literal("x")))
    g.add((E("local"), RDFS.label, Literal("y")))
    prefixes = dict(PREFIXES)
    align.register_prefixes(g, prefixes)
    assert prefixes["oth"] == "http://other.org/ns#"
    assert load_yaml(project / "prefixes.yaml")["oth"] == "http://other.org/ns#"


def aligned_zoo(iteration, project, **align_to):
    data = zoo()
    for term in data["glossary"]:
        term["align_to"] = align_to.get(term["term"].replace(" ", "_"), "")
    it = iteration(data=data, aligned=True)
    out = project / "refactoring" / it.name
    return it, Graph().parse(out / "tbox.ttl"), Graph().parse(out / "abox.ttl")


def test_main_replaces_aligned_terms_everywhere(iteration, project):
    it, tbox, abox = aligned_zoo(iteration, project, animal="voc:Creature", eats="voc:feedsOn")
    assert (E("Mammal"), RDFS.subClassOf, V("Creature")) in tbox
    assert (V("feedsOn"), RDFS.domain, V("Creature")) in tbox  # copied from the vocabulary
    assert any(isinstance(o, BNode) for o in tbox.objects(V("feedsOn"), RDFS.comment))
    assert not set(tbox.subjects(None, None)) & {E("Animal"), E("eats")}
    assert (E("rex"), V("feedsOn"), E("tom")) in abox and (E("tom"), RDF.type, V("Creature")) in abox
    query = load_yaml(it / "requirements.yaml")["competency_questions"][0]["refactored_query"]
    assert f"<{VOC}feedsOn>" in query


def test_main_links_aligned_classes_through_vocabulary_superclasses(iteration, project):
    _, tbox, _ = aligned_zoo(iteration, project, animal="voc:Creature", mammal="voc:Pet")
    assert (V("Pet"), RDFS.subClassOf, V("Domestic")) in tbox  # copied with Pet
    assert (V("Domestic"), RDFS.subClassOf, V("Creature")) in tbox  # climbed: leads to a relevant class
    assert (V("Agent"), RDFS.subClassOf, V("Being")) not in tbox  # leads nowhere relevant


def test_main_types_literals_with_the_aligned_range(iteration, project):
    _, _, abox = aligned_zoo(iteration, project, has_legs="voc:legCount")
    assert (E("rex"), V("legCount"), Literal("4", datatype=XSD.integer)) in abox


def test_main_reuses_current_model_terms(iteration, project, capsys):
    (project / "project").mkdir()
    (project / "project" / "tbox.ttl").write_text(graph(
        ':Beast a owl:Class ; rdfs:label "beast"@en ; rdfs:isDefinedBy : .').serialize(format="turtle"))
    _, tbox, abox = aligned_zoo(iteration, project, animal=":Beast")
    assert (E("Beast"), RDFS.label, Literal("beast", lang="en")) in tbox
    assert (E("tom"), RDF.type, E("Beast")) in abox
    assert "Warning" not in capsys.readouterr().out


def test_main_warns_when_the_vocabulary_lacks_the_term(iteration, project, capsys):
    aligned_zoo(iteration, project, animal="voc:Missing")
    assert "no triples for <http://example.com/voc/Missing>" in capsys.readouterr().out


def test_main_types_plain_literals_with_the_vocabulary_range(iteration, project):
    data = zoo()
    data["glossary"][3]["align_to"] = "voc:legCount"
    data["glossary"][3]["rules"] = {"domain": "animal"}  # no local range: abox.ttl has a plain "4"
    it = iteration(data=data, aligned=True)
    assert (E("rex"), V("legCount"), Literal("4", datatype=XSD.integer)) in Graph().parse(
        project / "refactoring" / it.name / "abox.ttl")


class FakeReply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_prefix_for_sources_in_order(monkeypatch):
    ns = "http://data.example.net/onto/core.owl#"
    assert align.prefix_for(ns, {ns: "known"}, set()) == "known"
    assert align.prefix_for(ns, {}, set()) == "core"  # network fails: last path segment, extension dropped
    assert align.prefix_for("urn:", {}, set()) == "urn"
    assert align.prefix_for("http://1.2/", {}, set()) == "ns"
    monkeypatch.setattr(align, "urlopen", lambda url, timeout: FakeReply(b'{"cc": "' + ns.encode() + b'"}'))
    assert align.prefix_for(ns, {}, set()) == "cc"

    def own_rdf(self, source=None, **kwargs):
        self.bind("self", ns)
        return self
    monkeypatch.setattr(align.Graph, "parse", own_rdf)
    assert align.prefix_for(ns, {}, set()) == "self"
    assert align.prefix_for(ns, {}, {"self"}) == "cc"  # taken names are skipped


def test_register_prefixes_resolves_name_clashes(project):
    g = Graph()
    g.bind("voc", "http://other.org/voc#")
    g.add((URIRef("http://other.org/voc#x"), RDFS.label, Literal("x")))
    prefixes = dict(PREFIXES)
    align.register_prefixes(g, prefixes)
    assert prefixes["voc2"] == "http://other.org/voc#"


def test_vocabulary_is_fetched_once_and_cached(project, monkeypatch):
    calls = []
    real_parse = Graph.parse

    def fetch(self, source=None, **kwargs):
        if str(source).startswith("http"):
            calls.append(source)
            return real_parse(self, data=VOCAB.replace("voc:", "oth:").replace(VOC, "http://other.org/"), format="turtle")
        return real_parse(self, source, **kwargs)

    monkeypatch.setattr(align.Graph, "parse", fetch)
    prefixes = {"oth": "http://other.org/"}
    g = align.vocabulary("http://other.org/Creature", prefixes)
    assert (URIRef("http://other.org/Creature"), RDF.type, OWL.Class) in g
    assert align.vocabulary("http://other.org/Agent", prefixes) is g and calls == ["http://other.org/"]
    assert (project / "vocabularies" / "oth.ttl").exists()
