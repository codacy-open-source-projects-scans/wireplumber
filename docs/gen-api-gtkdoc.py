#!/usr/bin/env python
#
#  Copyright 2015 The Geany contributors
#  Copyright 2021 Collabora Ltd.
#    @author George Kiagiadakis <george.kiagiadakis@collabora.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

import os
import sys
import re
from lxml import etree
from optparse import OptionParser


def normalize_text(s):
    r"""
    Normalizes whitespace in text.
    >>> normalize_text("asd xxx")
    'asd xxx'
    >>> normalize_text(" asd\nxxx  ")
    'asd xxx'
    """
    return s.replace("\n", " ").strip()


CXX_NAMESPACE_RE = re.compile(r'[_a-zA-Z][_0-9a-zA-Z]*::')
def fix_definition(s):
    """
    Removes C++ name qualifications from some definitions.
    For example:
    >>> fix_definition("bool flag")
    'bool flag'
    >>> fix_definition("bool FooBar::flag")
    'bool flag'
    >>> fix_definition("void(* _GeanyObjectClass::project_open) (GKeyFile *keyfile)")
    'void(* project_open) (GKeyFile *keyfile)'
    """
    return CXX_NAMESPACE_RE.sub(r"", s)


class AtDoc(object):
    def __init__(self):
        self.retval = None
        self.since = ""
        self.annot = []

    def cb(self, type, str):
        if (type == "param"):
            words = str.split(" ", 2)
            self.annot = []
        elif (type == "return"):
            self.annot = []
        elif (type == "since"):
            self.since = str.rstrip()
        elif (type == "see"):
            return "See " + str
        elif type in ("a", "c") and str in ("NULL", "TRUE", "FALSE"):
            return "%" + str
        elif (type == "a"):
            return "@" + str
        else:
            return str

        return ""


class DoxygenProcess(object):
    def __init__(self):
        self.at = None

    # http://stackoverflow.com/questions/4624062/get-all-text-inside-a-tag-in-lxml
    @staticmethod
    def stringify_children(node):
        from lxml.etree import tostring
        from itertools import chain
        parts = ([node.text] +
                 list(chain(*([c.text, tostring(c).decode("utf-8"), c.tail] for c in node.getchildren()))) +
                 [node.tail])
        # filter removes possible Nones in texts and tails
        return "".join(filter(None, parts))

    def get_program_listing(self, xml):
        from lxml.etree import tostring
        arr = ["", "|[<!-- language=\"C\" -->"]
        for l in xml.getchildren():
            if (l.tag == "codeline"):
                # a codeline is of the form
                # <highlight class="normal">GeanyDocument<sp/>*doc<sp/>=<sp/>...;</highlight>
                # <sp/> tags must be replaced with spaces, then just use the text
                h = l.find("highlight")
                if h is not None:
                    html = tostring(h).decode("utf-8")
                    html = html.replace("<sp/>", " ")
                    arr.append("  " + tostring(etree.HTML(html), method="text").decode("utf-8"))
        arr.append("]|")
        return "\n".join(arr)

    def join_annot(self):
        s = " ".join(map(lambda x: "(%s)" % x, self.at.annot))
        return s + ": " if s else ""

    def process_element(self, xml):
        self.at = AtDoc()
        s = self.__process_element(xml)
        return s

    def get_extra(self):
        return self.join_annot()

    def get_return(self):
        return self.at.retval

    def get_since(self):
        return self.at.since

    def __process_element(self, xml):
        s = ""

        if xml.text and re.search(r'\S', xml.text):
            s += xml.text
        for n in xml.getchildren():
            if n.tag == "emphasis":
                s += self.at.cb("a", self.__process_element(n))
            if n.tag == "computeroutput":
                s += self.at.cb("c", self.__process_element(n))
            if n.tag == "itemizedlist":
                s += "\n" + self.__process_element(n)
            if n.tag == "listitem":
                s += " - " + self.__process_element(n)
            if n.tag == "para":
                p = self.__process_element(n)
                if re.search(r'\S', p):
                    s += p + "\n"
            if n.tag == "ref":
                s += n.text if n.text else ""
            if n.tag == "simplesect":
                ss = self.at.cb(n.get("kind"), self.__process_element(n))
                s += ss + "\n" if ss else ""
            if n.tag == "programlisting":
                s += self.get_program_listing(n)
            if n.tag == "xrefsect":
                s += self.__process_element(n)
            if n.tag == "xreftitle":
                s += self.__process_element(n) + ": "
            if n.tag == "xrefdescription":
                s += self.__process_element(n)
            if n.tag == "ulink":
                s += self.__process_element(n)
            if n.tag == "linebreak":
                s += "\n"
            if n.tag == "ndash":
                s += "--"
                # workaround for doxygen bug #646002
            if n.tag == "htmlonly":
                s += ""
            if n.tail:
                if re.search(r'\S', n.tail):
                  s += n.tail
            if n.tag.startswith("param"):
                pass  # parameters are handled separately in DoxyFunction::from_memberdef()
        return s


class DoxyMember(object):
    def __init__(self, name, brief, extra=""):
        self.name       = name
        self.brief      = brief
        self.extra      = extra


class DoxyElement(object):

    def __init__(self, name, definition, **kwargs):
        self.name       = name
        self.definition = definition
        self.brief      = kwargs.get('brief', "")
        self.detail     = kwargs.get('detail', "")
        self.members    = kwargs.get('members', [])
        self.since      = kwargs.get('since', "")
        self.extra      = kwargs.get('extra', "")
        self.retval     = kwargs.get('retval', None)

    def is_documented(self):
        return (normalize_text(self.brief) != "" or
                normalize_text(self.detail) != "" or
                normalize_text(self.since) != "")

    def add_brief(self, xml):
        proc = DoxygenProcess()
        self.brief = proc.process_element(xml)
        self.extra += proc.get_extra()

    def add_detail(self, xml):
        proc = DoxygenProcess()
        self.detail = proc.process_element(xml)
        self.extra += proc.get_extra()
        self.since = proc.get_since()

    def add_member(self, xml):
        name = xml.find("name").text
        proc = DoxygenProcess()
        brief = proc.process_element(xml.find("briefdescription"))
        # optional doxygen command output appears within <detaileddescription />
        proc.process_element(xml.find("detaileddescription"))
        self.members.append(DoxyMember(name, normalize_text(brief), proc.get_extra()))

    def add_param(self, xml):
        name = xml.find("parameternamelist").find("parametername").text
        proc = DoxygenProcess()
        brief = proc.process_element(xml.find("parameterdescription"))
        self.members.append(DoxyMember(name, normalize_text(brief), proc.get_extra()))

    def add_return(self, xml):
        proc = DoxygenProcess()
        brief = proc.process_element(xml)
        self.retval = DoxyMember("ret", normalize_text(brief), proc.get_extra())

    def to_gtkdoc(self):
        s = []
        s.append("/**")
        s.append(" * %s: %s" % (self.name, self.extra))
        for p in self.members:
            s.append(" * @%s: %s %s" % (p.name, p.extra, p.brief))
        s.append(" *")
        s.append(" * %s" % self.brief.replace("\n", "\n * "))
        s.append(" *")
        s.append(" * %s" % self.detail.replace("\n", "\n * "))
        s.append(" *")
        if self.retval:
            s.append(" * Returns: %s %s" % (self.retval.extra, self.retval.brief))
        if self.since:
            s.append(" *")
            s.append(" * Since: %s" % self.since)
        s.append(" */")
        s.append("")
        return "\n".join(s)


class DoxyTypedef(DoxyElement):
    @staticmethod
    def from_memberdef(xml):
        name = xml.find("name").text
        d = normalize_text(xml.find("definition").text)
        d += ";"
        return DoxyTypedef(name, d)


class DoxyEnum(DoxyElement):
    @staticmethod
    def from_memberdef(xml):
        name = xml.find("name").text
        d = "typedef enum {\n"
        for member in xml.findall("enumvalue"):
            v = member.find("initializer")
            d += "\t%s%s,\n" % (member.find("name").text, " "+v.text if v is not None else "")
        d += "} %s;\n" % name

        e = DoxyEnum(name, d)
        e.add_brief(xml.find("briefdescription"))
        e.add_detail(xml.find("detaileddescription"))
        for p in xml.findall("enumvalue"):
            e.add_member(p)
        return e


class DoxyStruct(DoxyElement):
    @staticmethod
    def from_compounddef(xml, typedefs=[]):
        name = xml.find("compoundname").text
        d = "struct %s {\n" % name
        memberdefs = xml.xpath(".//sectiondef[@kind='public-attrib']/memberdef")
        for p in memberdefs:
            # workaround for struct members. g-ir-scanner can't properly map struct members
            # (beginning with struct GeanyFoo) to the typedef and assigns a generic type for them
            # thus we fix that up here and enforce usage of the typedef. These are written
            # out first, before any struct definition, for this reason
            # Exception: there are no typedefs for GeanyFooPrivate so skip those. Their exact
            # type isn't needed anyway
            s = fix_definition(p.find("definition").text).lstrip()
            proc = DoxygenProcess()
            brief = proc.process_element(p.find("briefdescription"))
            private = (normalize_text(brief) == "")
            words = s.split()
            if (words[0] == "struct"):
                if not (words[1].endswith("Private") or words[1].endswith("Private*")):
                    s = " ".join(words[1:])
            d += "\t/*< %s >*/\n\t%s;\n" % ("private" if private else "public", s)

        d += "};\n"
        e = DoxyStruct(name, d)
        e.add_brief(xml.find("briefdescription"))
        e.add_detail(xml.find("detaileddescription"))
        for p in memberdefs:
            e.add_member(p)
        return e


class DoxyFunction(DoxyElement):
    @staticmethod
    def from_memberdef(xml):
        name = xml.find("name").text
        d = normalize_text(xml.find("definition").text)
        if ((xml.find("argsstring").text) is not None):
            d += " " + xml.find("argsstring").text + ";"
            d = normalize_text(d)

        e = DoxyFunction(name, d)
        if (xml.get("prot") == "private"):
            e.extra = "(skip)"
        e.add_brief(xml.find("briefdescription"))
        e.add_detail(xml.find("detaileddescription"))
        for p in xml.xpath(".//detaileddescription/*/parameterlist[@kind='param']/parameteritem"):
            e.add_param(p)
        x = xml.xpath(".//detaileddescription/*/simplesect[@kind='return']")
        if (len(x) > 0):
            e.add_return(x[0])
        return e


class DoxyVariable(DoxyElement):
    @staticmethod
    def from_memberdef(xml):
        name = xml.find("name").text
        d = normalize_text(xml.find("definition").text)
        d += ";"
        e = DoxyVariable(name, d)
        e.add_brief(xml.find("briefdescription"))
        t = xml.find("type")
        if t is not None:
            typestr = "".join(t.itertext()).strip()
            if typestr.startswith("const "):
                typestr = typestr[6:]
            e.type = "("+typestr+") "
        else:
            e.type = ""
        v = xml.find("initializer")
        e.value = v.text.replace("=","").replace("\n","") if v is not None else ""
        return e
    def to_gtkdoc(self):
        s = super().to_gtkdoc()
        # need this to get g-ir-scanner to recognize this as a constant
        s += "#define "+self.name+" ("+self.type+self.value+")\n"
        s += "#undef "+self.name+"\n"
        return s


def main(args):
    xml_dir = None
    outfile = None

    parser = OptionParser(usage="usage: %prog [options] XML_DIR")
    parser.add_option("-o", "--output", metavar="FILE", help="Write output to FILE",
                      action="store", dest="outfile")
    opts, args = parser.parse_args(args[1:])

    xml_dir = args[0]

    if not (os.path.exists(xml_dir)):
        sys.stderr.write("invalid xml directory\n")
        return 1

    symbols = []
    transform = etree.XSLT(etree.parse(os.path.join(xml_dir, "combine.xslt")))
    doc = etree.parse(os.path.join(xml_dir, "index.xml"))
    root = transform(doc)
    h_files = root.xpath(".//compounddef[@kind='file']/compoundname[substring(.,string-length(.)-1)='.h']/..")

    for f in h_files:
        for n0 in f.xpath(".//*/memberdef[@kind='enum']"):
            e = DoxyEnum.from_memberdef(n0)
            symbols.append(e)

    for n0 in root.xpath(".//compounddef[@kind='struct']"):
        e = DoxyStruct.from_compounddef(n0)
        symbols.append(e)

    for n0 in root.xpath(".//compounddef[@kind='group']"):
        for n1 in n0.xpath(".//*/memberdef[@kind='function']"):
            e = DoxyFunction.from_memberdef(n1)
            symbols.append(e)
        for n1 in n0.xpath(".//*/memberdef[@kind='variable']"):
            e = DoxyVariable.from_memberdef(n1)
            symbols.append(e)

    if (opts.outfile):
        try:
            outfile = open(opts.outfile, "w+")
        except OSError as err:
            sys.stderr.write("failed to open \"%s\" for writing (%s)\n" % (opts.outfile, err.strerror))
            return 1
    else:
        outfile = sys.stdout

    try:
        outfile.write("/*\n * Automatically generated file - do not edit\n */\n\n")

        for e in filter(lambda x: x.is_documented(), symbols):
            outfile.write("\n")
            outfile.write(e.to_gtkdoc())
            outfile.write("\n")

    except BrokenPipeError:
        # probably piped to head or tail
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
